from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from pos.models import Category, DiningTable, MenuItem, Order, OrderItem, Payment, Setting
from pos import services


class Phase5BillingTests(TestCase):
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

    def _create_sample_order(self, waiter=None):
        waiter = waiter or self.waiter
        order = services.create_order(table=self.table, waiter=waiter)
        services.add_item_to_order(order, self.menu_item1.pk, quantity=2)
        services.add_item_to_order(order, self.menu_item2.pk, quantity=1)
        services.send_order_to_kitchen(order)
        order.refresh_from_db()
        return order

    # -------------------------------------------------------------------------
    # 1. Access Control Tests
    # -------------------------------------------------------------------------

    def test_billing_list_access_permissions(self):
        url = reverse("billing")

        # Cashier allowed
        self.client.login(username="cashier", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "pos/billing/list.html")

        # Manager allowed
        self.client.login(username="manager", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # Admin allowed
        self.client.login(username="admin", password="admin123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # Waiter denied
        self.client.login(username="waiter", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Kitchen denied
        self.client.login(username="kitchen", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # Anonymous redirects to login
        self.client.logout()
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)

    def test_billing_detail_access_permissions(self):
        order = self._create_sample_order()
        url = reverse("billing_detail", kwargs={"order_id": order.pk})

        # Cashier allowed
        self.client.login(username="cashier", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "pos/billing/detail.html")

        # Waiter denied
        self.client.login(username="waiter", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

    # -------------------------------------------------------------------------
    # 2. Billing Calculations (Decimal & 2 Decimal Places)
    # -------------------------------------------------------------------------

    def test_order_totals_and_decimal_precision(self):
        order = self._create_sample_order()
        expected_subtotal = (self.menu_item1.price * 2 + self.menu_item2.price).quantize(Decimal("0.01"))
        self.assertEqual(order.subtotal, expected_subtotal)

        # Check tax calculation
        expected_tax = ((expected_subtotal - order.discount) * order.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        self.assertEqual(order.tax, expected_tax)

        # Check total calculation
        expected_total = (expected_subtotal - order.discount + expected_tax).quantize(Decimal("0.01"))
        self.assertEqual(order.total, expected_total)
        self.assertEqual(order.paid_amount, Decimal("0.00"))
        self.assertEqual(order.remaining_balance, expected_total)
        self.assertFalse(order.is_paid)

    # -------------------------------------------------------------------------
    # 3. Discount Rule Tests
    # -------------------------------------------------------------------------

    def test_valid_discount_application(self):
        order = self._create_sample_order()
        subtotal = order.subtotal
        discount_to_apply = Decimal("50.00")
        self.assertLess(discount_to_apply, subtotal)

        services.apply_order_discount(order, discount_to_apply)
        order.refresh_from_db()

        self.assertEqual(order.discount, Decimal("50.00"))
        expected_tax = ((subtotal - Decimal("50.00")) * order.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        self.assertEqual(order.tax, expected_tax)
        self.assertEqual(order.total, (subtotal - Decimal("50.00") + expected_tax).quantize(Decimal("0.01")))

    def test_discount_cannot_be_negative(self):
        order = self._create_sample_order()
        # Direct service call
        with self.assertRaises(ValueError) as ctx:
            services.apply_order_discount(order, Decimal("-10.00"))
        self.assertIn("Discount cannot be negative", str(ctx.exception))

        # View POST
        self.client.login(username="cashier", password="demo123")
        res = self.client.post(reverse("billing_discount", kwargs={"order_id": order.pk}), {"discount": "-15.00"})
        self.assertEqual(res.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.discount, Decimal("0.00"))

    def test_discount_cannot_exceed_subtotal(self):
        order = self._create_sample_order()
        excess_discount = order.subtotal + Decimal("100.00")

        # Direct service call
        with self.assertRaises(ValueError) as ctx:
            services.apply_order_discount(order, excess_discount)
        self.assertIn("Discount cannot exceed order subtotal", str(ctx.exception))

        # View POST
        self.client.login(username="cashier", password="demo123")
        res = self.client.post(reverse("billing_discount", kwargs={"order_id": order.pk}), {"discount": str(excess_discount)})
        self.assertEqual(res.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.discount, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # 4. Payment Rule Tests
    # -------------------------------------------------------------------------

    def test_payment_amount_must_be_greater_than_zero(self):
        order = self._create_sample_order()

        # Direct service call with 0
        with self.assertRaises(ValueError) as ctx:
            services.record_payment(order, self.cashier, Payment.Method.CASH, Decimal("0.00"))
        self.assertIn("greater than zero", str(ctx.exception))

        # Direct service call with negative amount
        with self.assertRaises(ValueError) as ctx:
            services.record_payment(order, self.cashier, Payment.Method.CASH, Decimal("-50.00"))
        self.assertIn("greater than zero", str(ctx.exception))

        # View POST
        self.client.login(username="cashier", password="demo123")
        res = self.client.post(
            reverse("billing_pay", kwargs={"order_id": order.pk}),
            {"method": "cash", "amount": "0"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(order.payments.count(), 0)

    def test_cancelled_order_cannot_be_paid(self):
        order = self._create_sample_order()
        services.cancel_order(order)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

        # Direct service call
        with self.assertRaises(ValueError) as ctx:
            services.record_payment(order, self.cashier, Payment.Method.CASH, Decimal("100.00"))
        self.assertIn("cancelled order cannot be paid", str(ctx.exception).lower())

        # View POST
        self.client.login(username="cashier", password="demo123")
        res = self.client.post(
            reverse("billing_pay", kwargs={"order_id": order.pk}),
            {"method": "cash", "amount": "100.00"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(order.payments.count(), 0)

    def test_split_payments_and_order_completion(self):
        order = self._create_sample_order()
        table = order.table
        self.assertEqual(table.status, DiningTable.Status.OCCUPIED)

        total_due = order.total
        self.assertGreater(total_due, Decimal("200.00"))

        # 1st Payment: Partial Cash Payment
        part1 = Decimal("100.00")
        pay1, change1, is_comp1 = services.record_payment(
            order=order,
            cashier=self.cashier,
            method=Payment.Method.CASH,
            amount=part1,
            reference="Split Part 1",
            tendered=Decimal("100.00"),
        )
        self.assertFalse(is_comp1)
        self.assertEqual(change1, Decimal("0.00"))
        order.refresh_from_db()
        table.refresh_from_db()

        self.assertEqual(order.payments.count(), 1)
        self.assertEqual(order.paid_amount, Decimal("100.00"))
        self.assertEqual(order.remaining_balance, total_due - Decimal("100.00"))
        self.assertNotEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(table.status, DiningTable.Status.OCCUPIED)

        # 2nd Payment: Settle Remaining with Card via View POST
        remaining = order.remaining_balance
        self.client.login(username="cashier", password="demo123")
        res = self.client.post(
            reverse("billing_pay", kwargs={"order_id": order.pk}),
            {
                "method": "card",
                "amount": str(remaining),
                "reference": "AUTH-9876",
            },
        )
        self.assertEqual(res.status_code, 302)
        order.refresh_from_db()
        table.refresh_from_db()

        # Verify completed status, closed_at set, table freed
        self.assertEqual(order.payments.count(), 2)
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertIsNotNone(order.closed_at)
        self.assertTrue(order.is_paid)
        self.assertEqual(order.remaining_balance, Decimal("0.00"))
        self.assertEqual(table.status, DiningTable.Status.FREE)

    def test_cash_payment_change_due_calculation(self):
        order = self._create_sample_order()
        total_due = order.total
        tendered_cash = total_due + Decimal("150.00")

        pay, change_due, is_completed = services.record_payment(
            order=order,
            cashier=self.cashier,
            method=Payment.Method.CASH,
            amount=total_due,
            tendered=tendered_cash,
        )
        self.assertTrue(is_completed)
        self.assertEqual(change_due, Decimal("150.00"))
        self.assertEqual(pay.amount, total_due)

    # -------------------------------------------------------------------------
    # 5. Cancellation Rule Tests
    # -------------------------------------------------------------------------

    def test_completed_order_can_never_be_cancelled(self):
        order = self._create_sample_order()
        # Fully pay and complete order
        services.record_payment(order, self.cashier, Payment.Method.CARD, order.total)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

        # Attempt to cancel via service
        with self.assertRaises(ValueError) as ctx:
            services.cancel_order(order, user=self.admin, reason="Customer complained")
        self.assertIn("completed order cannot be cancelled", str(ctx.exception).lower())

        # Attempt to cancel via view POST
        self.client.login(username="admin", password="admin123")
        res = self.client.post(reverse("order_cancel", kwargs={"order_id": order.pk}), {"reason": "Test"})
        self.assertEqual(res.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

    def test_cancellation_with_in_progress_items_requires_manager_and_reason(self):
        order = self._create_sample_order()
        # Mark one item as preparing
        first_item = order.items.first()
        services.update_order_item_status(first_item, OrderItem.Status.PREPARING, user=self.kitchen)
        order.refresh_from_db()
        self.assertTrue(order.has_in_progress_or_served_items)

        # 1. Waiter cannot cancel an order when items are preparing/ready/served
        with self.assertRaises(PermissionDenied):
            services.cancel_order(order, user=self.waiter, reason="Customer had to leave")

        # 2. Manager cannot cancel without entering a reason
        with self.assertRaises(ValueError) as ctx:
            services.cancel_order(order, user=self.manager, reason="")
        self.assertIn("reason must be entered", str(ctx.exception).lower())

        with self.assertRaises(ValueError) as ctx:
            services.cancel_order(order, user=self.manager, reason="   ")
        self.assertIn("reason must be entered", str(ctx.exception).lower())

        # 3. Manager can cancel with a valid non-empty reason
        table = order.table
        self.assertEqual(table.status, DiningTable.Status.OCCUPIED)

        services.cancel_order(order, user=self.manager, reason="Customer emergency; table vacated")
        order.refresh_from_db()
        table.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertIn("Customer emergency; table vacated", order.notes)
        self.assertEqual(table.status, DiningTable.Status.FREE)

    def test_pending_order_cancellation_by_waiter(self):
        # Fresh order with all items pending
        table = DiningTable.objects.filter(status=DiningTable.Status.FREE).first()
        order = services.create_order(table=table, waiter=self.waiter)
        services.add_item_to_order(order, self.menu_item1.pk, quantity=1)

        self.assertFalse(order.has_in_progress_or_served_items)

        # Waiter can cancel pending order
        services.cancel_order(order, user=self.waiter)
        order.refresh_from_db()
        table.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(table.status, DiningTable.Status.FREE)

    # -------------------------------------------------------------------------
    # 6. PDF Receipt Generation Tests
    # -------------------------------------------------------------------------

    def test_pdf_receipt_download(self):
        order = self._create_sample_order()
        services.record_payment(order, self.cashier, Payment.Method.CASH, order.total)
        order.refresh_from_db()

        url = reverse("billing_receipt_pdf", kwargs={"order_id": order.pk})

        # Cashier download
        self.client.login(username="cashier", password="demo123")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertIn(f"receipt_order_{order.pk}.pdf", res["Content-Disposition"])
        self.assertTrue(res.content.startswith(b"%PDF-"))
