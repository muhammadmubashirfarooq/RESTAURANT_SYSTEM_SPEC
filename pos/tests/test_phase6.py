import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from pos.models import Category, DiningTable, MenuItem, Order, OrderItem, Payment, Setting
from pos import services


class Phase6DashboardAndReportsTests(TestCase):
    def setUp(self):
        call_command("seed_demo")
        self.admin = User.objects.get(username="admin")
        self.manager = User.objects.get(username="manager")
        self.waiter = User.objects.get(username="waiter")
        self.kitchen = User.objects.get(username="kitchen")
        self.cashier = User.objects.get(username="cashier")

        self.table = DiningTable.objects.filter(status=DiningTable.Status.FREE).first()
        self.menu_item1 = MenuItem.objects.filter(is_available=True).first()
        self.menu_item2 = MenuItem.objects.filter(is_available=True).last()
        self.setting = Setting.objects.first()

    # -------------------------------------------------------------------------
    # 1. Access Control Tests
    # -------------------------------------------------------------------------

    def test_dashboard_access_permissions(self):
        url = reverse("dashboard")

        # Admin allowed
        self.client.login(username="admin", password="admin123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "pos/dashboard.html")

        # Manager allowed
        self.client.login(username="manager", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # Waiter denied (403)
        self.client.login(username="waiter", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Kitchen denied (403)
        self.client.login(username="kitchen", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Cashier denied (403)
        self.client.login(username="cashier", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Anonymous redirects to login (302)
        self.client.logout()
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)

    def test_reports_access_permissions(self):
        url = reverse("reports")

        # Admin allowed
        self.client.login(username="admin", password="admin123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "pos/reports/index.html")

        # Manager allowed
        self.client.login(username="manager", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # Waiter denied (403)
        self.client.login(username="waiter", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Kitchen denied (403)
        self.client.login(username="kitchen", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Cashier denied (403)
        self.client.login(username="cashier", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Anonymous redirects to login (302)
        self.client.logout()
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)

    def test_reports_csv_export_access_permissions(self):
        url = reverse("reports_export_csv")

        # Admin allowed
        self.client.login(username="admin", password="admin123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/csv; charset=utf-8")

        # Manager allowed
        self.client.login(username="manager", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # Waiter denied
        self.client.login(username="waiter", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Cashier denied
        self.client.login(username="cashier", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Anonymous redirects to login
        self.client.logout()
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)

    # -------------------------------------------------------------------------
    # 2. Dashboard Calculation Tests (KPIs, Charts, Top Items)
    # -------------------------------------------------------------------------

    def test_dashboard_kpis_calculation(self):
        # Create a fresh completed order today to guarantee today's sales exist
        order = services.create_order(table=self.table, waiter=self.waiter)
        services.add_item_to_order(order, self.menu_item1.pk, quantity=2)
        services.send_order_to_kitchen(order)
        services.record_payment(
            order, cashier=self.cashier, method=Payment.Method.CASH, amount=order.total
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

        metrics = services.get_dashboard_metrics()
        today = timezone.localdate()

        # Recalculate directly from DB
        today_completed = Order.objects.filter(status=Order.Status.COMPLETED, created_at__date=today)
        expected_today_sales = sum((o.total for o in today_completed), Decimal("0.00")).quantize(Decimal("0.01"))
        expected_today_orders = today_completed.count()
        expected_aov = (expected_today_sales / Decimal(str(expected_today_orders))).quantize(Decimal("0.01"))

        self.assertEqual(metrics["today_sales"], expected_today_sales)
        self.assertEqual(metrics["today_orders_count"], expected_today_orders)
        self.assertEqual(metrics["today_aov"], expected_aov)
        self.assertIsInstance(metrics["today_sales"], Decimal)
        self.assertIsInstance(metrics["today_aov"], Decimal)

    def test_cancelled_orders_excluded_from_sales(self):
        # Create an order and cancel it
        order = services.create_order(table=self.table, waiter=self.waiter)
        services.add_item_to_order(order, self.menu_item1.pk, quantity=5)
        services.cancel_order(order, user=self.admin, reason="Customer left")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

        metrics_before = services.get_dashboard_metrics()
        today = timezone.localdate()

        # Cancelled order should not be counted in today's sales
        completed_today = Order.objects.filter(status=Order.Status.COMPLETED, created_at__date=today)
        self.assertNotIn(order, completed_today)

        # And reports data should not include this cancelled order
        report = services.get_reports_data(today, today)
        self.assertEqual(report["grand_orders_count"], completed_today.count())

    def test_top_5_items_calculation(self):
        top_items = services.get_dashboard_top_items(limit=5)
        self.assertLessEqual(len(top_items), 5)

        # Verify items are ordered descending by quantity sold
        quantities = [item["quantity"] for item in top_items]
        self.assertEqual(quantities, sorted(quantities, reverse=True))

        for item in top_items:
            self.assertIn("rank", item)
            self.assertIn("name", item)
            self.assertIn("category", item)
            self.assertIsInstance(item["revenue"], Decimal)
            self.assertIsInstance(item["price"], Decimal)

    def test_last_7_days_sales_trend(self):
        trend = services.get_dashboard_sales_trend(days=7)
        self.assertEqual(len(trend), 7)

        today = timezone.localdate()
        expected_dates = [today - timedelta(days=i) for i in range(6, -1, -1)]
        actual_dates = [item["date"] for item in trend]
        self.assertEqual(actual_dates, expected_dates)

        for day_data in trend:
            self.assertIsInstance(day_data["sales"], Decimal)
            self.assertIsInstance(day_data["sales_float"], float)
            self.assertGreaterEqual(day_data["orders_count"], 0)

    def test_orders_by_status_distribution(self):
        status_data = services.get_dashboard_orders_by_status()
        self.assertEqual(len(status_data), 6)  # 6 choices in Order.Status

        total_orders_in_chart = sum(item["count"] for item in status_data)
        self.assertEqual(total_orders_in_chart, Order.objects.count())

    # -------------------------------------------------------------------------
    # 3. Reports Calculations (Daily, Item, Payment Method)
    # -------------------------------------------------------------------------

    def test_reports_data_calculations(self):
        today = timezone.localdate()
        start_date = today - timedelta(days=14)
        end_date = today

        report = services.get_reports_data(start_date, end_date)

        # 1. Orders count matches DB
        completed_in_range = Order.objects.filter(
            status=Order.Status.COMPLETED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        self.assertEqual(report["grand_orders_count"], completed_in_range.count())

        # 2. Sales by day sum matches grand_sales
        daily_sales_sum = sum((row["total"] for row in report["sales_by_day"]), Decimal("0.00")).quantize(Decimal("0.01"))
        self.assertEqual(report["grand_sales"], daily_sales_sum)

        # 3. Sum of payment methods matches grand payment amount
        pm_sales_sum = sum((pm["total_amount"] for pm in report["sales_by_payment_method"]), Decimal("0.00")).quantize(Decimal("0.01"))
        self.assertEqual(report["grand_payment_amount"], pm_sales_sum)

        # 4. Each currency amount is Decimal and rounded to 2 decimal places
        for row in report["sales_by_day"]:
            self.assertIsInstance(row["total"], Decimal)
            self.assertIsInstance(row["subtotal"], Decimal)
            self.assertIsInstance(row["discount"], Decimal)
            self.assertIsInstance(row["tax"], Decimal)
            self.assertIsInstance(row["aov"], Decimal)

        for pm in report["sales_by_payment_method"]:
            self.assertIsInstance(pm["total_amount"], Decimal)
            self.assertIn(pm["method"], [Payment.Method.CASH, Payment.Method.CARD, Payment.Method.ONLINE])

    def test_reports_date_filtering_boundaries(self):
        # A date in the distant future should have 0 sales
        future_date = timezone.localdate() + timedelta(days=365)
        report = services.get_reports_data(future_date, future_date)

        self.assertEqual(report["grand_orders_count"], 0)
        self.assertEqual(report["grand_sales"], Decimal("0.00"))
        self.assertEqual(report["grand_subtotal"], Decimal("0.00"))
        self.assertEqual(len(report["sales_by_day"]), 0)
        self.assertEqual(len(report["sales_by_item"]), 0)

    # -------------------------------------------------------------------------
    # 4. CSV Export Tests
    # -------------------------------------------------------------------------

    def test_reports_csv_export_content(self):
        today = timezone.localdate()
        start_date = today - timedelta(days=14)
        end_date = today

        self.client.login(username="admin", password="admin123")
        url = f"{reverse('reports_export_csv')}?start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
        res = self.client.get(url)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=", res["Content-Disposition"])

        content = res.content.decode("utf-8")
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)

        # Verify headers exist
        header_row = None
        for r in rows:
            if "Order ID" in r:
                header_row = r
                break
        self.assertIsNotNone(header_row)
        self.assertIn("Total Sales (PKR)", header_row)
        self.assertIn("Items Count", header_row)

        # Verify TOTALS footer row exists
        totals_row = rows[-1]
        self.assertEqual(totals_row[0], "TOTALS")
