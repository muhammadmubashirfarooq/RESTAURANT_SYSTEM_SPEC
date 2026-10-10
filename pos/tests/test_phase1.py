from decimal import Decimal
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from pos.models import Category, MenuItem, DiningTable, Order, OrderItem, Payment, Setting


class Phase1FoundationTests(TestCase):
    def setUp(self):
        call_command("seed_demo")

    def test_seed_demo_created_objects(self):
        self.assertTrue(Group.objects.filter(name="Admin").exists())
        self.assertTrue(Group.objects.filter(name="Manager").exists())
        self.assertTrue(Group.objects.filter(name="Waiter").exists())
        self.assertTrue(Group.objects.filter(name="Kitchen").exists())
        self.assertTrue(Group.objects.filter(name="Cashier").exists())

        self.assertTrue(User.objects.filter(username="admin").exists())
        self.assertTrue(User.objects.filter(username="manager").exists())
        self.assertTrue(User.objects.filter(username="waiter").exists())
        self.assertTrue(User.objects.filter(username="kitchen").exists())
        self.assertTrue(User.objects.filter(username="cashier").exists())

        self.assertGreaterEqual(Category.objects.count(), 6)
        self.assertGreaterEqual(MenuItem.objects.count(), 25)
        self.assertEqual(DiningTable.objects.count(), 12)
        self.assertGreaterEqual(Order.objects.count(), 40)
        self.assertIsNotNone(Setting.objects.first())

    def test_order_calculations(self):
        category = Category.objects.first()
        item1 = MenuItem.objects.create(category=category, name="Test Item 1", price=Decimal("500.00"))
        item2 = MenuItem.objects.create(category=category, name="Test Item 2", price=Decimal("300.00"))

        table = DiningTable.objects.first()
        waiter = User.objects.get(username="waiter")
        order = Order.objects.create(table=table, waiter=waiter, discount=Decimal("50.00"), tax_rate=Decimal("10.00"))

        OrderItem.objects.create(order=order, menu_item=item1, quantity=2, unit_price=item1.price) # 1000
        OrderItem.objects.create(order=order, menu_item=item2, quantity=1, unit_price=item2.price) # 300

        self.assertEqual(order.subtotal, Decimal("1300.00"))
        # Tax = (1300 - 50) * 10 / 100 = 125.00
        self.assertEqual(order.tax, Decimal("125.00"))
        # Total = 1300 - 50 + 125 = 1375.00
        self.assertEqual(order.total, Decimal("1375.00"))
        self.assertFalse(order.is_paid)

        Payment.objects.create(order=order, cashier=User.objects.get(username="cashier"), method="cash", amount=Decimal("1375.00"))
        self.assertTrue(order.is_paid)

    def test_role_based_login_redirects(self):
        # Waiter login -> /tables/
        response_waiter = self.client.post(reverse("login"), {"username": "waiter", "password": "demo123"}, follow=True)
        self.assertRedirects(response_waiter, reverse("tables"))
        self.client.logout()

        # Kitchen login -> /kitchen/
        response_kitchen = self.client.post(reverse("login"), {"username": "kitchen", "password": "demo123"}, follow=True)
        self.assertRedirects(response_kitchen, reverse("kitchen"))
        self.client.logout()

        # Cashier login -> /billing/
        response_cashier = self.client.post(reverse("login"), {"username": "cashier", "password": "demo123"}, follow=True)
        self.assertRedirects(response_cashier, reverse("billing"))
        self.client.logout()

        # Manager login -> /dashboard/
        response_manager = self.client.post(reverse("login"), {"username": "manager", "password": "demo123"}, follow=True)
        self.assertRedirects(response_manager, reverse("dashboard"))
        self.client.logout()

    def test_role_permissions_access_control(self):
        # Unauthenticated access to dashboard redirects to login
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

        # Login as Waiter
        self.client.login(username="waiter", password="demo123")
        # Waiter accessing dashboard (admin/manager only) yields 403 Forbidden
        response_dash = self.client.get(reverse("dashboard"))
        self.assertEqual(response_dash.status_code, 403)

        # Waiter accessing tables yields 200 OK
        response_tables = self.client.get(reverse("tables"))
        self.assertEqual(response_tables.status_code, 200)
