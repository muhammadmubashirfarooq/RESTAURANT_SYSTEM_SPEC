from decimal import Decimal
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.http import Http404

from pos.models import Category, DiningTable, MenuItem, Order, OrderItem, Payment, Setting
from pos import services
from pos.views.errors import custom_404_view, custom_500_view


class Phase7PolishAndDeployTests(TestCase):
    def setUp(self):
        call_command("seed_demo")
        self.admin = User.objects.get(username="admin")
        self.manager = User.objects.get(username="manager")
        self.waiter = User.objects.get(username="waiter")

    # -------------------------------------------------------------------------
    # 1. seed_demo Repeatable Execution Tests
    # -------------------------------------------------------------------------

    def test_seed_demo_safe_repeated_runs(self):
        """Verify running seed_demo multiple times maintains consistent data without duplicating demo orders."""
        initial_order_count = Order.objects.filter(notes="Demo historical order").count()
        self.assertEqual(initial_order_count, 40)

        # Run seed_demo again
        call_command("seed_demo")
        second_order_count = Order.objects.filter(notes="Demo historical order").count()
        self.assertEqual(second_order_count, 40)

        # Run a third time
        call_command("seed_demo")
        third_order_count = Order.objects.filter(notes="Demo historical order").count()
        self.assertEqual(third_order_count, 40)

        # All tables should be reset to FREE
        self.assertEqual(
            DiningTable.objects.filter(status=DiningTable.Status.OCCUPIED).count(), 0
        )
        self.assertEqual(
            DiningTable.objects.filter(status=DiningTable.Status.FREE).count(), 12
        )

    # -------------------------------------------------------------------------
    # 2. Friendly Custom Error Pages (404 and 500)
    # -------------------------------------------------------------------------

    def test_custom_404_view(self):
        """Verify custom 404 view returns status 404 and uses pos/404.html template."""
        res = self.client.get("/non-existent-endpoint-404/")
        self.assertEqual(res.status_code, 404)
        self.assertTemplateUsed(res, "pos/404.html")
        self.assertContains(res, "404", status_code=404)
        self.assertContains(res, "Page Not Found", status_code=404)

    def test_custom_500_view(self):
        """Verify custom 500 view returns status 500 and uses pos/500.html template."""
        # Directly call custom_500_view
        response = custom_500_view(None)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"500", response.content)
        self.assertIn(b"Kitchen Hiccup!", response.content)

    # -------------------------------------------------------------------------
    # 3. Production Settings & Database Configuration
    # -------------------------------------------------------------------------

    def test_database_url_parser(self):
        """Verify dj_database_url parses postgres database URLs properly."""
        import dj_database_url

        db_url = "postgres://pos_user:secure_pass@db.example.com:5432/pos_production"
        parsed = dj_database_url.parse(db_url)
        self.assertEqual(parsed["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(parsed["NAME"], "pos_production")
        self.assertEqual(parsed["USER"], "pos_user")
        self.assertEqual(parsed["PASSWORD"], "secure_pass")
        self.assertEqual(parsed["HOST"], "db.example.com")
        self.assertEqual(parsed["PORT"], 5432)

    # -------------------------------------------------------------------------
    # 4. UI Empty States
    # -------------------------------------------------------------------------

    def test_dashboard_empty_state_when_no_completed_orders(self):
        """Dashboard renders clean empty state when no completed orders exist."""
        Order.objects.all().delete()
        self.client.login(username="admin", password="admin123")
        res = self.client.get(reverse("dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "No completed orders found")

    def test_billing_empty_state_when_no_open_orders(self):
        """Billing list renders clean empty state when no open orders await payment."""
        Order.objects.exclude(status=Order.Status.COMPLETED).delete()
        self.client.login(username="admin", password="admin123")
        res = self.client.get(reverse("billing"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "All caught up!")

    def test_login_page_renders_high_contrast_credentials(self):
        """Login page displays high contrast demo logins with clear User/Pass labels."""
        res = self.client.get(reverse("login"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Demo Accounts")
        self.assertContains(res, "admin123")
        self.assertNotContains(res, "Phase 1 Foundation")
