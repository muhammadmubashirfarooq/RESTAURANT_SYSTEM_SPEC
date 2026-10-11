from decimal import Decimal
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from pos.models import Category, DiningTable, MenuItem, Order, OrderItem, Setting
from pos import services


class Phase3OrderTakingTests(TestCase):
    def setUp(self):
        call_command("seed_demo")
        self.admin = User.objects.get(username="admin")
        self.manager = User.objects.get(username="manager")
        self.waiter = User.objects.get(username="waiter")
        self.kitchen = User.objects.get(username="kitchen")
        self.cashier = User.objects.get(username="cashier")

        # Make sure we have a known free table
        self.free_table = DiningTable.objects.filter(status=DiningTable.Status.FREE).first()
        if not self.free_table:
            self.free_table = DiningTable.objects.create(name="T-TestFree", capacity=4, status=DiningTable.Status.FREE)

        self.client.login(username="waiter", password="demo123")

    def test_tables_view_access(self):
        response = self.client.get(reverse("tables"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pos/tables.html")
        self.assertIn("table_list", response.context)
        self.assertIn("stats", response.context)

    def test_order_creation_sets_table_occupied(self):
        # Initial status is free
        self.assertEqual(self.free_table.status, DiningTable.Status.FREE)

        # Waiter starts new order for free table
        response = self.client.get(reverse("order_new", kwargs={"table_id": self.free_table.pk}))
        self.free_table.refresh_from_db()

        # Rule: Creating an order on a table sets the table to occupied.
        self.assertEqual(self.free_table.status, DiningTable.Status.OCCUPIED)

        order = services.get_active_order_for_table(self.free_table)
        self.assertIsNotNone(order)
        self.assertEqual(order.waiter, self.waiter)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertRedirects(response, reverse("order_detail", kwargs={"order_id": order.pk}))

    def test_order_creation_on_occupied_table_redirects_to_active_order(self):
        # Create an active order first
        order1 = services.create_order(table=self.free_table, waiter=self.waiter)
        self.free_table.refresh_from_db()
        self.assertEqual(self.free_table.status, DiningTable.Status.OCCUPIED)

        # Attempt to create another order on the same table
        response = self.client.get(reverse("order_new", kwargs={"table_id": self.free_table.pk}))
        self.assertRedirects(response, reverse("order_detail", kwargs={"order_id": order1.pk}))

    def test_order_detail_view(self):
        order = services.create_order(table=self.free_table, waiter=self.waiter)
        response = self.client.get(reverse("order_detail", kwargs={"order_id": order.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pos/orders/detail.html")
        self.assertEqual(response.context["order"], order)

    def test_add_item_to_order_regular_and_htmx(self):
        order = services.create_order(table=self.free_table, waiter=self.waiter)
        item = MenuItem.objects.filter(is_available=True).first()

        # Add item via HTMX POST
        response = self.client.post(
            reverse("order_add_item", kwargs={"order_id": order.pk}),
            {"menu_item_id": item.pk, "quantity": 2},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pos/orders/cart_partial.html")

        # Verify OrderItem exists
        order_item = order.items.get(menu_item=item)
        self.assertEqual(order_item.quantity, 2)
        # Rule: unit_price is copied from menu at order time
        self.assertEqual(order_item.unit_price, item.price)

        # Add same item again -> increments quantity
        self.client.post(
            reverse("order_add_item", kwargs={"order_id": order.pk}),
            {"menu_item_id": item.pk, "quantity": 1},
            HTTP_HX_REQUEST="true",
        )
        order_item.refresh_from_db()
        self.assertEqual(order_item.quantity, 3)

    def test_cannot_add_unavailable_menu_item(self):
        order = services.create_order(table=self.free_table, waiter=self.waiter)
        unavail_item = MenuItem.objects.create(
            category=Category.objects.first(),
            name="Sold Out Item",
            price=Decimal("500.00"),
            is_available=False,
        )

        # Trying to add unavailable item
        response = self.client.post(
            reverse("order_add_item", kwargs={"order_id": order.pk}),
            {"menu_item_id": unavail_item.pk, "quantity": 1},
            follow=True,
        )
        self.assertFalse(order.items.filter(menu_item=unavail_item).exists())

    def test_update_item_quantity_and_delete_on_zero(self):
        order = services.create_order(table=self.free_table, waiter=self.waiter)
        item = MenuItem.objects.filter(is_available=True).first()
        order_item = services.add_item_to_order(order, item.pk, quantity=2)

        # Increment (+1)
        self.client.post(
            reverse("order_update_item", kwargs={"order_id": order.pk, "item_id": order_item.pk}),
            {"delta": "1"},
            HTTP_HX_REQUEST="true",
        )
        order_item.refresh_from_db()
        self.assertEqual(order_item.quantity, 3)

        # Decrement (-2)
        self.client.post(
            reverse("order_update_item", kwargs={"order_id": order.pk, "item_id": order_item.pk}),
            {"delta": "-2"},
            HTTP_HX_REQUEST="true",
        )
        order_item.refresh_from_db()
        self.assertEqual(order_item.quantity, 1)

        # Decrement (-1) to 0 -> should delete item
        self.client.post(
            reverse("order_update_item", kwargs={"order_id": order.pk, "item_id": order_item.pk}),
            {"delta": "-1"},
            HTTP_HX_REQUEST="true",
        )
        self.assertFalse(order.items.filter(pk=order_item.pk).exists())

    def test_update_item_note(self):
        order = services.create_order(table=self.free_table, waiter=self.waiter)
        item = MenuItem.objects.filter(is_available=True).first()
        order_item = services.add_item_to_order(order, item.pk, quantity=1)

        self.client.post(
            reverse("order_update_item", kwargs={"order_id": order.pk, "item_id": order_item.pk}),
            {"note": "No spice, extra sauce"},
            HTTP_HX_REQUEST="true",
        )
        order_item.refresh_from_db()
        self.assertEqual(order_item.note, "No spice, extra sauce")

    def test_remove_order_item(self):
        order = services.create_order(table=self.free_table, waiter=self.waiter)
        item = MenuItem.objects.filter(is_available=True).first()
        order_item = services.add_item_to_order(order, item.pk, quantity=1)

        self.client.post(
            reverse("order_remove_item", kwargs={"order_id": order.pk, "item_id": order_item.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertFalse(order.items.filter(pk=order_item.pk).exists())

    def test_subtotal_tax_and_total_calculations(self):
        setting = Setting.objects.first()
        setting.tax_rate = Decimal("10.00")
        setting.save()

        order = services.create_order(table=self.free_table, waiter=self.waiter)
        item1 = MenuItem.objects.create(category=Category.objects.first(), name="Item A", price=Decimal("100.00"))
        item2 = MenuItem.objects.create(category=Category.objects.first(), name="Item B", price=Decimal("200.00"))

        services.add_item_to_order(order, item1.pk, quantity=2)  # 200
        services.add_item_to_order(order, item2.pk, quantity=1)  # 200

        # Subtotal = 400.00
        self.assertEqual(order.subtotal, Decimal("400.00"))
        # Tax = 400 * 10% = 40.00
        self.assertEqual(order.tax, Decimal("40.00"))
        # Total = 440.00
        self.assertEqual(order.total, Decimal("440.00"))

    def test_send_order_to_kitchen(self):
        order = services.create_order(table=self.free_table, waiter=self.waiter)

        # Cannot send empty order
        response_empty = self.client.post(
            reverse("order_send", kwargs={"order_id": order.pk}),
            follow=True,
        )
        self.assertContains(response_empty, "Cannot send an empty order")

        # Add item and send
        item = MenuItem.objects.filter(is_available=True).first()
        services.add_item_to_order(order, item.pk, quantity=1)

        response = self.client.post(
            reverse("order_send", kwargs={"order_id": order.pk}),
            follow=True,
        )
        self.assertRedirects(response, reverse("tables"))

        # Table turns / stays occupied (red)
        self.free_table.refresh_from_db()
        self.assertEqual(self.free_table.status, DiningTable.Status.OCCUPIED)

    def test_cancel_order_frees_table(self):
        order = services.create_order(table=self.free_table, waiter=self.waiter)
        item = MenuItem.objects.filter(is_available=True).first()
        services.add_item_to_order(order, item.pk, quantity=1)

        self.free_table.refresh_from_db()
        self.assertEqual(self.free_table.status, DiningTable.Status.OCCUPIED)

        # Waiter cancels order
        response = self.client.post(
            reverse("order_cancel", kwargs={"order_id": order.pk}),
            follow=True,
        )
        self.assertRedirects(response, reverse("tables"))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

        # Rule: A cancelled order frees the table.
        self.free_table.refresh_from_db()
        self.assertEqual(self.free_table.status, DiningTable.Status.FREE)

    def test_role_access_control(self):
        order = services.create_order(table=self.free_table, waiter=self.waiter)
        self.client.logout()

        # Kitchen user cannot open order detail or create orders
        self.client.login(username="kitchen", password="demo123")
        res_kitchen = self.client.get(reverse("order_detail", kwargs={"order_id": order.pk}))
        self.assertEqual(res_kitchen.status_code, 403)

        self.client.logout()
        # Cashier user cannot open order detail or create orders
        self.client.login(username="cashier", password="demo123")
        res_cashier = self.client.get(reverse("order_detail", kwargs={"order_id": order.pk}))
        self.assertEqual(res_cashier.status_code, 403)
