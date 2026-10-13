import os
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from pos.models import Category, DiningTable, MenuItem, Order, OrderItem, Setting
from pos import services


class Phase4KitchenTests(TestCase):
    def setUp(self):
        call_command("seed_demo")
        self.admin = User.objects.get(username="admin")
        self.manager = User.objects.get(username="manager")
        self.waiter = User.objects.get(username="waiter")
        self.kitchen = User.objects.get(username="kitchen")
        self.cashier = User.objects.get(username="cashier")

        self.table = DiningTable.objects.first()
        self.menu_item1 = MenuItem.objects.first()
        self.menu_item2 = MenuItem.objects.last()

    def _create_sample_order(self, waiter=None):
        waiter = waiter or self.waiter
        order = services.create_order(table=self.table, waiter=waiter)
        services.add_item_to_order(order, self.menu_item1.pk, quantity=2, note="No onions")
        services.add_item_to_order(order, self.menu_item2.pk, quantity=1, note="Spicy")
        services.send_order_to_kitchen(order)
        order.refresh_from_db()
        return order

    # -------------------------------------------------------------------------
    # 1. Access Control Tests
    # -------------------------------------------------------------------------

    def test_kitchen_board_access_permissions(self):
        # Kitchen user allowed
        self.client.login(username="kitchen", password="demo123")
        res_kitchen = self.client.get(reverse("kitchen"))
        self.assertEqual(res_kitchen.status_code, 200)
        self.assertTemplateUsed(res_kitchen, "pos/kitchen/board.html")

        # Manager user allowed
        self.client.login(username="manager", password="demo123")
        res_mgr = self.client.get(reverse("kitchen"))
        self.assertEqual(res_mgr.status_code, 200)

        # Admin user allowed
        self.client.login(username="admin", password="admin123")
        res_admin = self.client.get(reverse("kitchen"))
        self.assertEqual(res_admin.status_code, 200)

        # Waiter denied
        self.client.login(username="waiter", password="demo123")
        res_waiter = self.client.get(reverse("kitchen"))
        self.assertEqual(res_waiter.status_code, 403)

        # Cashier denied
        self.client.login(username="cashier", password="demo123")
        res_cashier = self.client.get(reverse("kitchen"))
        self.assertEqual(res_cashier.status_code, 403)

        # Anonymous redirected
        self.client.logout()
        res_anon = self.client.get(reverse("kitchen"))
        self.assertEqual(res_anon.status_code, 302)

    def test_kitchen_partial_access_permissions(self):
        self.client.login(username="kitchen", password="demo123")
        res = self.client.get(reverse("kitchen_partial"))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "pos/kitchen/board_partial.html")

        # Waiter denied
        self.client.login(username="waiter", password="demo123")
        res_waiter = self.client.get(reverse("kitchen_partial"))
        self.assertEqual(res_waiter.status_code, 403)

    # -------------------------------------------------------------------------
    # 2. Server-side Permission Checks on Item Status Changes
    # -------------------------------------------------------------------------

    def test_item_status_transitions_by_kitchen(self):
        order = self._create_sample_order()
        item1 = order.items.first()
        self.assertEqual(item1.status, OrderItem.Status.PENDING)

        # Kitchen moves pending -> preparing
        self.client.login(username="kitchen", password="demo123")
        res1 = self.client.post(
            reverse("kitchen_item_status", kwargs={"item_id": item1.pk}),
            {"status": "preparing"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(res1.status_code, 200)
        item1.refresh_from_db()
        self.assertEqual(item1.status, OrderItem.Status.PREPARING)

        # Kitchen moves preparing -> ready
        res2 = self.client.post(
            reverse("kitchen_item_status", kwargs={"item_id": item1.pk}),
            {"status": "ready"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(res2.status_code, 200)
        item1.refresh_from_db()
        self.assertEqual(item1.status, OrderItem.Status.READY)

    def test_waiter_cannot_change_to_preparing_or_ready(self):
        order = self._create_sample_order()
        item1 = order.items.first()

        self.client.login(username="waiter", password="demo123")

        # Waiter tries to set 'preparing' -> 403 Forbidden
        res = self.client.post(
            reverse("kitchen_item_status", kwargs={"item_id": item1.pk}),
            {"status": "preparing"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(res.status_code, 403)
        item1.refresh_from_db()
        self.assertEqual(item1.status, OrderItem.Status.PENDING)

        # Waiter tries to set 'ready' -> 403 Forbidden
        res2 = self.client.post(
            reverse("kitchen_item_status", kwargs={"item_id": item1.pk}),
            {"status": "ready"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(res2.status_code, 403)
        item1.refresh_from_db()
        self.assertEqual(item1.status, OrderItem.Status.PENDING)

    def test_waiter_can_mark_ready_items_as_served(self):
        order = self._create_sample_order()
        item1 = order.items.first()

        # Kitchen prepares and marks item1 ready
        self.client.login(username="kitchen", password="demo123")
        self.client.post(
            reverse("kitchen_item_status", kwargs={"item_id": item1.pk}),
            {"status": "ready"},
            HTTP_HX_REQUEST="true",
        )
        item1.refresh_from_db()
        self.assertEqual(item1.status, OrderItem.Status.READY)

        # Waiter marks ready item as served
        self.client.login(username="waiter", password="demo123")
        res = self.client.post(
            reverse("kitchen_item_status", kwargs={"item_id": item1.pk}),
            {"status": "served", "source": "order"},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="order-cart",
        )
        self.assertEqual(res.status_code, 200)
        item1.refresh_from_db()
        self.assertEqual(item1.status, OrderItem.Status.SERVED)
        self.assertTemplateUsed(res, "pos/orders/cart_partial.html")

    # -------------------------------------------------------------------------
    # 3. Order Status Derivation Rules
    # -------------------------------------------------------------------------

    def test_order_status_derived_from_items(self):
        order = self._create_sample_order()
        items = list(order.items.all())
        item1, item2 = items[0], items[1]

        # Initial state: both pending -> order is pending
        self.assertEqual(order.status, Order.Status.PENDING)

        # 1 item preparing -> order is preparing
        services.update_order_item_status(item1, OrderItem.Status.PREPARING, self.kitchen)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PREPARING)

        # 1 item ready, 1 item preparing -> order is preparing
        services.update_order_item_status(item1, OrderItem.Status.READY, self.kitchen)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PREPARING)

        # ALL items ready -> order is ready
        services.update_order_item_status(item2, OrderItem.Status.READY, self.kitchen)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.READY)

        # 1 item served, 1 item still ready -> order is ready
        services.update_order_item_status(item1, OrderItem.Status.SERVED, self.waiter)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.READY)

        # ALL items served -> order is served
        services.update_order_item_status(item2, OrderItem.Status.SERVED, self.waiter)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SERVED)

    # -------------------------------------------------------------------------
    # 4. Kitchen Board Display & Batch Actions
    # -------------------------------------------------------------------------

    def test_kitchen_board_cards_and_columns(self):
        order = self._create_sample_order()
        self.client.login(username="kitchen", password="demo123")

        response = self.client.get(reverse("kitchen_partial"))
        self.assertEqual(response.status_code, 200)

        # Verify columns exist
        self.assertIn("pending_orders", response.context)
        self.assertIn("preparing_orders", response.context)
        self.assertIn("ready_orders", response.context)

        # Pending order shows table name, order number, and items with notes
        content = response.content.decode()
        self.assertIn(f"#{order.pk}", content)
        self.assertIn(self.table.name, content)
        self.assertIn(self.menu_item1.name, content)
        self.assertIn("No onions", content)
        self.assertIn("NEW", content)  # highlighted as new

        # Test batch status action: Start All Items
        batch_res = self.client.post(
            reverse("kitchen_order_batch_status", kwargs={"order_id": order.pk}),
            {"status": "preparing"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(batch_res.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PREPARING)
        for it in order.items.all():
            self.assertEqual(it.status, OrderItem.Status.PREPARING)

        # Test batch status action: Mark All Ready
        batch_ready_res = self.client.post(
            reverse("kitchen_order_batch_status", kwargs={"order_id": order.pk}),
            {"status": "ready"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(batch_ready_res.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.READY)
        for it in order.items.all():
            self.assertEqual(it.status, OrderItem.Status.READY)

    def test_waiter_order_cart_endpoint_and_live_status(self):
        order = self._create_sample_order()
        item1 = order.items.first()
        services.update_order_item_status(item1, OrderItem.Status.READY, self.kitchen)

        self.client.login(username="waiter", password="demo123")
        res = self.client.get(reverse("order_cart", kwargs={"order_id": order.pk}))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "pos/orders/cart_partial.html")

        content = res.content.decode()
        self.assertIn("Ready", content)
        self.assertIn("Mark Served", content)

    # -------------------------------------------------------------------------
    # 5. Housekeeping Requirements
    # -------------------------------------------------------------------------

    def test_seed_demo_creates_or_updates_demo_users_correctly(self):
        call_command("seed_demo")

        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password("admin123"))
        self.assertTrue(admin.groups.filter(name="Admin").exists())

        for username, role_name in [
            ("manager", "Manager"),
            ("waiter", "Waiter"),
            ("kitchen", "Kitchen"),
            ("cashier", "Cashier"),
        ]:
            u = User.objects.get(username=username)
            self.assertTrue(u.is_active, f"{username} should be active")
            self.assertFalse(u.is_staff, f"{username} should not be staff")
            self.assertFalse(u.is_superuser, f"{username} should not be superuser")
            self.assertTrue(u.check_password("demo123"), f"{username} password should be demo123")
            self.assertTrue(u.groups.filter(name=role_name).exists(), f"{username} should have {role_name} group")

    def test_temporary_media_root_used_in_tests(self):
        # Ensure MEDIA_ROOT is not pointing directly to real project media directory
        real_media_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "media"))
        active_media_root = os.path.abspath(str(settings.MEDIA_ROOT))
        self.assertNotEqual(
            active_media_root,
            real_media_dir,
            "Test suite must use temporary MEDIA_ROOT and not write into the real media folder.",
        )
