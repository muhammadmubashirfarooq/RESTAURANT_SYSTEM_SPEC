from decimal import Decimal
from django.urls import reverse
from django.db import transaction
from .models import DiningTable, Order, OrderItem, MenuItem, Setting, Payment
from .permissions import get_user_role


def get_role_redirect_url(user):
    """
    Role-based redirect URLs after login (Section 3):
    Admin/Manager -> Dashboard (/dashboard/)
    Waiter -> Tables (/tables/)
    Kitchen -> Kitchen screen (/kitchen/)
    Cashier -> Billing list (/billing/)
    """
    role = get_user_role(user)
    if role in ["Admin", "Manager"]:
        return reverse("dashboard")
    elif role == "Waiter":
        return reverse("tables")
    elif role == "Kitchen":
        return reverse("kitchen")
    elif role == "Cashier":
        return reverse("billing")
    return reverse("dashboard")


def get_active_order_for_table(table):
    """Return the active open order for a table if any."""
    return Order.objects.filter(
        table=table
    ).exclude(
        status__in=[Order.Status.COMPLETED, Order.Status.CANCELLED]
    ).order_by("-created_at").first()


@transaction.atomic
def create_order(table, waiter, order_type=Order.Type.DINE_IN):
    """
    Creates an order on a table.
    Rule: Creating an order on a table sets the table to occupied.
    Tax rate is copied from Settings.
    """
    setting = Setting.objects.first()
    tax_rate = setting.tax_rate if setting else Decimal("0")

    order = Order.objects.create(
        table=table,
        waiter=waiter,
        order_type=order_type,
        status=Order.Status.PENDING,
        tax_rate=tax_rate,
    )

    if table:
        table.status = DiningTable.Status.OCCUPIED
        table.save(update_fields=["status"])

    return order


@transaction.atomic
def add_item_to_order(order, menu_item_id, quantity=1, note=""):
    """
    Adds a menu item to an order or increments quantity if item already exists.
    Rule: Unavailable menu items cannot be added to an order.
    Rule: unit_price is copied from the menu at order time.
    """
    menu_item = MenuItem.objects.get(pk=menu_item_id)
    if not menu_item.is_available:
        raise ValueError(f"Menu item '{menu_item.name}' is currently unavailable.")

    clean_note = note.strip() if note else ""

    # Look for existing pending item with the same note
    existing_item = order.items.filter(
        menu_item=menu_item,
        status=OrderItem.Status.PENDING,
        note=clean_note,
    ).first()

    if existing_item:
        existing_item.quantity += quantity
        existing_item.save(update_fields=["quantity"])
        return existing_item
    else:
        return OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            quantity=quantity,
            unit_price=menu_item.price,
            status=OrderItem.Status.PENDING,
            note=clean_note,
        )


@transaction.atomic
def update_order_item_quantity(order, item_id, delta=None, new_quantity=None):
    """
    Updates quantity of an order item. If quantity <= 0, deletes item.
    """
    order_item = order.items.get(pk=item_id)
    if delta is not None:
        target_qty = order_item.quantity + delta
    elif new_quantity is not None:
        target_qty = new_quantity
    else:
        return order_item

    if target_qty <= 0:
        order_item.delete()
        return None
    else:
        order_item.quantity = target_qty
        order_item.save(update_fields=["quantity"])
        return order_item


@transaction.atomic
def update_order_item_note(order, item_id, note):
    """Updates special instructions note on an order item."""
    order_item = order.items.get(pk=item_id)
    order_item.note = note.strip()
    order_item.save(update_fields=["note"])
    return order_item


@transaction.atomic
def remove_order_item(order, item_id):
    """Removes an item from the order."""
    order_item = order.items.get(pk=item_id)
    order_item.delete()
    return True


@transaction.atomic
def send_order_to_kitchen(order):
    """
    Sends order to kitchen.
    Rule: Waiter opens a free table, adds items, sends order, table turns red (occupied).
    """
    if not order.items.exclude(status=OrderItem.Status.CANCELLED).exists():
        raise ValueError("Cannot send an empty order to the kitchen.")

    # Ensure table status is OCCUPIED
    if order.table and order.table.status != DiningTable.Status.OCCUPIED:
        order.table.status = DiningTable.Status.OCCUPIED
        order.table.save(update_fields=["status"])

    # Ensure order status is PENDING (ready for kitchen)
    if order.status != Order.Status.PENDING:
        order.status = Order.Status.PENDING
        order.save(update_fields=["status"])

    return order


@transaction.atomic
def cancel_order(order, user=None, reason=""):
    """
    Cancels an order and frees the table.
    Rules enforced on SERVER:
    - A completed (paid) order can never be cancelled.
    - If any item is already preparing/ready/served, only Manager or Admin can cancel the order, and a reason must be entered.
    - A cancelled order frees the table.
    """
    from django.core.exceptions import PermissionDenied
    from pos.permissions import is_manager

    # Rule: A completed (paid) order can never be cancelled
    if order.status == Order.Status.COMPLETED or order.is_paid:
        raise ValueError("A completed order cannot be cancelled.")

    # Rule: If any item is already preparing/ready/served, only Manager or Admin can cancel, with reason
    has_in_progress = order.items.filter(
        status__in=[OrderItem.Status.PREPARING, OrderItem.Status.READY, OrderItem.Status.SERVED]
    ).exists()

    if has_in_progress:
        if user is not None and not is_manager(user):
            raise PermissionDenied("Only Manager or Admin can cancel an order that has items in preparation or served.")
        
        clean_reason = reason.strip() if reason else ""
        if not clean_reason:
            raise ValueError("A cancellation reason must be entered when cancelling an order with prepared or served items.")
        
        if order.notes:
            order.notes = f"{order.notes}\nCancellation reason: {clean_reason}".strip()
        else:
            order.notes = f"Cancellation reason: {clean_reason}"
    else:
        clean_reason = reason.strip() if reason else ""
        if clean_reason:
            if order.notes:
                order.notes = f"{order.notes}\nCancellation reason: {clean_reason}".strip()
            else:
                order.notes = f"Cancellation reason: {clean_reason}"

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "notes"])

    # Cancel all non-cancelled items
    order.items.exclude(status=OrderItem.Status.CANCELLED).update(status=OrderItem.Status.CANCELLED)

    # Free table
    if order.table:
        order.table.status = DiningTable.Status.FREE
        order.table.save(update_fields=["status"])

    return order


@transaction.atomic
def sync_order_status(order):
    """
    Derives order status from its non-cancelled items:
    - all ready = order ready
    - all served = order served
    - any preparing / partially ready = order preparing
    - all pending = order pending
    """
    if order.status in [Order.Status.COMPLETED, Order.Status.CANCELLED]:
        return order.status

    active_items = order.items.exclude(status=OrderItem.Status.CANCELLED)
    if not active_items.exists():
        return order.status

    statuses = set(active_items.values_list("status", flat=True))

    if statuses == {OrderItem.Status.SERVED}:
        new_status = Order.Status.SERVED
    elif statuses.issubset({OrderItem.Status.READY, OrderItem.Status.SERVED}):
        new_status = Order.Status.READY
    elif any(s in [OrderItem.Status.PREPARING, OrderItem.Status.READY, OrderItem.Status.SERVED] for s in statuses):
        new_status = Order.Status.PREPARING
    else:
        new_status = Order.Status.PENDING

    if order.status != new_status:
        order.status = new_status
        order.save(update_fields=["status"])

    return order.status


@transaction.atomic
def update_order_item_status(order_item, new_status, user):
    """
    Updates status of an order item with role permission checks:
    - Kitchen, Manager, Admin can change to 'preparing' or 'ready'.
    - Waiter, Kitchen, Manager, Admin can mark ready items as 'served'.
    """
    from django.core.exceptions import PermissionDenied
    from pos.permissions import is_kitchen, is_waiter

    # Server-side role checks
    if new_status in [OrderItem.Status.PREPARING, OrderItem.Status.READY]:
        if not is_kitchen(user):
            raise PermissionDenied("Only Kitchen, Manager, and Admin can update kitchen preparation status.")
    elif new_status == OrderItem.Status.SERVED:
        if not is_waiter(user):
            raise PermissionDenied("Only Waiter, Kitchen, Manager, and Admin can mark items as served.")

    order_item.status = new_status
    order_item.save(update_fields=["status"])

    sync_order_status(order_item.order)
    return order_item


@transaction.atomic
def update_order_all_items_status(order, new_status, user):
    """
    Batch updates all active items of an order to the given status.
    """
    from django.core.exceptions import PermissionDenied
    from pos.permissions import is_kitchen, is_waiter

    if new_status in [OrderItem.Status.PREPARING, OrderItem.Status.READY]:
        if not is_kitchen(user):
            raise PermissionDenied("Only Kitchen, Manager, and Admin can update kitchen preparation status.")
    elif new_status == OrderItem.Status.SERVED:
        if not is_waiter(user):
            raise PermissionDenied("Only Waiter, Kitchen, Manager, and Admin can mark items as served.")

    items_to_update = order.items.exclude(status=OrderItem.Status.CANCELLED)
    for item in items_to_update:
        item.status = new_status
        item.save(update_fields=["status"])

    sync_order_status(order)
    return order


def get_kitchen_board_data():
    """
    Retrieves and categorizes active orders for the Kitchen Board into 3 columns:
    Pending, Preparing, and Ready. Calculates elapsed time and flags new orders.
    """
    from django.utils import timezone

    orders = (
        Order.objects.filter(
            status__in=[Order.Status.PENDING, Order.Status.PREPARING, Order.Status.READY]
        )
        .select_related("table", "waiter")
        .prefetch_related("items__menu_item")
        .order_by("created_at")
    )

    now = timezone.now()
    pending_orders = []
    preparing_orders = []
    ready_orders = []

    for order in orders:
        elapsed_seconds = max(0, int((now - order.created_at).total_seconds()))
        order.elapsed_seconds = elapsed_seconds
        if elapsed_seconds < 60:
            order.elapsed_display = f"{elapsed_seconds}s ago"
        elif elapsed_seconds < 3600:
            mins = elapsed_seconds // 60
            order.elapsed_display = f"{mins}m ago"
        else:
            hrs = elapsed_seconds // 3600
            mins = (elapsed_seconds % 3600) // 60
            order.elapsed_display = f"{hrs}h {mins}m ago"

        # Highlight new orders: created within last 5 minutes and status is PENDING
        order.is_new = (order.status == Order.Status.PENDING and elapsed_seconds <= 300)

        # Separate items for quick display on card
        order.active_items = [item for item in order.items.all() if item.status != OrderItem.Status.CANCELLED]

        if order.status == Order.Status.PENDING:
            pending_orders.append(order)
        elif order.status == Order.Status.PREPARING:
            preparing_orders.append(order)
        elif order.status == Order.Status.READY:
            ready_orders.append(order)

    return {
        "pending_orders": pending_orders,
        "preparing_orders": preparing_orders,
        "ready_orders": ready_orders,
        "total_active": len(pending_orders) + len(preparing_orders) + len(ready_orders),
    }


def get_billing_orders():
    """
    Returns open orders for Cashier / Billing screen (Section 4 & 10).
    Open orders are those not completed and not cancelled.
    """
    return (
        Order.objects.exclude(
            status__in=[Order.Status.COMPLETED, Order.Status.CANCELLED]
        )
        .select_related("table", "waiter")
        .prefetch_related("items__menu_item", "payments")
        .order_by("-created_at")
    )


@transaction.atomic
def apply_order_discount(order, discount_amount):
    """
    Applies or updates a discount on an order.
    Rules enforced on SERVER:
    - Discount cannot be negative.
    - Discount cannot be more than the subtotal.
    - Uses Decimal and rounds to 2 decimal places.
    """
    try:
        discount = Decimal(str(discount_amount)).quantize(Decimal("0.01"))
    except Exception:
        raise ValueError("Invalid discount amount.")

    if discount < Decimal("0.00"):
        raise ValueError("Discount cannot be negative.")

    if discount > order.subtotal:
        raise ValueError("Discount cannot exceed order subtotal.")

    if order.status == Order.Status.CANCELLED:
        raise ValueError("Cannot apply discount to a cancelled order.")

    if order.status == Order.Status.COMPLETED:
        raise ValueError("Cannot apply discount to a completed order.")

    order.discount = discount
    order.save(update_fields=["discount"])
    return order


@transaction.atomic
def record_payment(order, cashier, method, amount, reference="", tendered=None):
    """
    Records a payment for an order. Split payments are supported.
    Rules enforced on SERVER:
    - A completed order cannot receive further payments.
    - A cancelled order cannot be paid.
    - Payment amount must be greater than zero.
    - When paid amount >= total: order becomes completed, closed_at is set, and table is freed.
    - All money calculations use Decimal with 2 decimal places.
    Returns: (payment, change_due, is_completed)
    """
    from django.utils import timezone

    if order.status == Order.Status.CANCELLED:
        raise ValueError("A cancelled order cannot be paid.")

    if order.status == Order.Status.COMPLETED:
        raise ValueError("A completed order is already fully paid.")

    try:
        amt = Decimal(str(amount)).quantize(Decimal("0.01"))
    except Exception:
        raise ValueError("Invalid payment amount.")

    if amt <= Decimal("0.00"):
        raise ValueError("Payment amount must be greater than zero.")

    # Calculate change due if tendered amount was provided
    change_due = Decimal("0.00")
    if tendered is not None and str(tendered).strip() != "":
        try:
            tend = Decimal(str(tendered)).quantize(Decimal("0.01"))
            if tend >= amt:
                change_due = (tend - amt).quantize(Decimal("0.01"))
        except Exception:
            pass

    # Cap payment to remaining balance if amount > remaining balance, excess treated as change
    remaining = order.remaining_balance
    if remaining <= Decimal("0.00"):
        raise ValueError("Order is already fully paid.")

    payment_amount = amt
    if amt > remaining:
        excess = amt - remaining
        change_due = (change_due + excess).quantize(Decimal("0.01"))
        payment_amount = remaining

    payment = Payment.objects.create(
        order=order,
        cashier=cashier,
        method=method,
        amount=payment_amount,
        reference=reference.strip() if reference else "",
    )

    # Refresh order to check completion
    order.refresh_from_db()
    is_completed = False

    if order.paid_amount >= order.total:
        order.status = Order.Status.COMPLETED
        order.closed_at = timezone.now()
        order.save(update_fields=["status", "closed_at"])

        if order.table:
            order.table.status = DiningTable.Status.FREE
            order.table.save(update_fields=["status"])
        is_completed = True

    return payment, change_due, is_completed


def generate_receipt_pdf(order):
    """
    Renders pure Python PDF receipt using xhtml2pdf.
    Includes restaurant name, address, phone, items, tax, discount, total, payment methods, date, order no.
    """
    from io import BytesIO
    from xhtml2pdf import pisa
    from django.template.loader import get_template

    template = get_template("pos/billing/receipt_pdf.html")
    setting = Setting.objects.first()
    context = {
        "order": order,
        "setting": setting,
        "items": order.items.exclude(status=OrderItem.Status.CANCELLED).select_related("menu_item"),
        "payments": order.payments.all().select_related("cashier").order_by("paid_at"),
    }
    html = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    if not pdf.err:
        return result.getvalue()
    return None


# =============================================================================
# Phase 6: Dashboard & Reports Services
# =============================================================================

def get_dashboard_metrics():
    """
    Returns KPI metrics for the Admin/Manager dashboard:
    - Today's sales: Sum of completed orders total today (Decimal, 2 decimal places).
    - Today's orders count: Count of completed orders today.
    - Today's average order value (AOV): today_sales / today_orders_count (Decimal, 2 decimal places).
    - All-time metrics: total completed orders, total revenue.
    Only completed (paid) orders count as sales; cancelled orders are excluded.
    """
    from django.utils import timezone

    today = timezone.localdate()
    today_completed_orders = Order.objects.filter(
        status=Order.Status.COMPLETED,
        created_at__date=today,
    )

    today_sales = sum((order.total for order in today_completed_orders), Decimal("0.00")).quantize(Decimal("0.01"))
    today_orders_count = today_completed_orders.count()

    if today_orders_count > 0:
        today_aov = (today_sales / Decimal(str(today_orders_count))).quantize(Decimal("0.01"))
    else:
        today_aov = Decimal("0.00")

    # All-time / Lifetime stats
    all_completed = Order.objects.filter(status=Order.Status.COMPLETED)
    lifetime_sales = sum((order.total for order in all_completed), Decimal("0.00")).quantize(Decimal("0.01"))
    lifetime_orders_count = all_completed.count()

    # Active tables / orders right now
    open_orders_count = Order.objects.exclude(
        status__in=[Order.Status.COMPLETED, Order.Status.CANCELLED]
    ).count()

    return {
        "today_date": today,
        "today_sales": today_sales,
        "today_orders_count": today_orders_count,
        "today_aov": today_aov,
        "lifetime_sales": lifetime_sales,
        "lifetime_orders_count": lifetime_orders_count,
        "open_orders_count": open_orders_count,
    }


def get_dashboard_top_items(limit=5):
    """
    Returns the top menu items by quantity sold from completed orders.
    Cancelled items and cancelled orders are excluded.
    Returns list of dicts with:
    - rank
    - id, name, category, price
    - quantity
    - revenue (Decimal, 2 decimal places)
    """
    from django.db.models import Sum, F

    items_qs = (
        OrderItem.objects.filter(order__status=Order.Status.COMPLETED)
        .exclude(status=OrderItem.Status.CANCELLED)
        .values(
            "menu_item__id",
            "menu_item__name",
            "menu_item__category__name",
            "menu_item__price",
        )
        .annotate(
            total_qty=Sum("quantity"),
            total_revenue=Sum(F("quantity") * F("unit_price")),
        )
        .order_by("-total_qty", "-total_revenue")[:limit]
    )

    top_items = []
    for idx, item in enumerate(items_qs, start=1):
        rev = item["total_revenue"] or Decimal("0.00")
        if not isinstance(rev, Decimal):
            rev = Decimal(str(rev))
        top_items.append({
            "rank": idx,
            "id": item["menu_item__id"],
            "name": item["menu_item__name"],
            "category": item["menu_item__category__name"] or "Uncategorized",
            "price": Decimal(str(item["menu_item__price"])).quantize(Decimal("0.01")),
            "quantity": item["total_qty"] or 0,
            "revenue": rev.quantize(Decimal("0.01")),
        })

    return top_items


def get_dashboard_sales_trend(days=7):
    """
    Returns the last N days sales for the Chart.js line chart.
    Each day has:
    - date: date object
    - date_str: YYYY-MM-DD
    - label: e.g. "Oct 19"
    - weekday: e.g. "Mon"
    - sales: Decimal (2 decimal places)
    - sales_float: float for Chart.js
    - orders_count: int
    """
    from django.utils import timezone
    from datetime import timedelta

    today = timezone.localdate()
    day_list = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]

    trend = []
    for d in day_list:
        day_completed_orders = Order.objects.filter(
            status=Order.Status.COMPLETED,
            created_at__date=d,
        )
        sales = sum((order.total for order in day_completed_orders), Decimal("0.00")).quantize(Decimal("0.01"))
        trend.append({
            "date": d,
            "date_str": d.isoformat(),
            "label": d.strftime("%b %d"),
            "weekday": d.strftime("%a"),
            "sales": sales,
            "sales_float": float(sales),
            "orders_count": day_completed_orders.count(),
        })

    return trend


def get_dashboard_orders_by_status():
    """
    Returns order counts grouped by status for Chart.js doughnut chart.
    Includes color codes and human-readable labels matching Order.Status.choices.
    """
    from django.db.models import Count

    status_counts = dict(
        Order.objects.values_list("status").annotate(count=Count("id"))
    )

    STATUS_CONFIG = {
        Order.Status.PENDING: {"label": "Pending", "color": "#f59e0b", "border": "#d97706"},
        Order.Status.PREPARING: {"label": "Preparing", "color": "#06b6d4", "border": "#0891b2"},
        Order.Status.READY: {"label": "Ready", "color": "#3b82f6", "border": "#2563eb"},
        Order.Status.SERVED: {"label": "Served", "color": "#8b5cf6", "border": "#7c3aed"},
        Order.Status.COMPLETED: {"label": "Completed", "color": "#10b981", "border": "#059669"},
        Order.Status.CANCELLED: {"label": "Cancelled", "color": "#ef4444", "border": "#dc2626"},
    }

    results = []
    for status_key, config in STATUS_CONFIG.items():
        cnt = status_counts.get(status_key, 0)
        results.append({
            "status": status_key,
            "label": config["label"],
            "count": cnt,
            "color": config["color"],
            "border": config["border"],
        })

    return results


def parse_date_range(start_date_str, end_date_str, default_days=30):
    """
    Parses and sanitizes start and end date strings.
    Defaults to last default_days ending today if missing or invalid.
    Ensures start_date <= end_date.
    """
    from django.utils import timezone
    from datetime import datetime, timedelta

    today = timezone.localdate()

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            end_date = today
    else:
        end_date = today

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            start_date = end_date - timedelta(days=default_days - 1)
    else:
        start_date = end_date - timedelta(days=default_days - 1)

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date


def get_reports_data(start_date=None, end_date=None):
    """
    Generates reports data for the given date range:
    1. Sales by Day
    2. Sales by Item
    3. Sales by Payment Method
    4. Grand Totals Summary
    Only completed orders are included in sales. Cancelled orders are excluded.
    All money amounts are Decimal with 2 decimal places.
    """
    from django.db.models import Sum, F, Count

    if start_date is None or end_date is None:
        start_date, end_date = parse_date_range(None, None)

    # 1. Base queryset of completed orders in date range
    completed_orders = (
        Order.objects.filter(
            status=Order.Status.COMPLETED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        .prefetch_related("items", "payments")
        .order_by("-created_at")
    )

    # Group completed orders by day
    orders_by_date = {}
    for order in completed_orders:
        o_date = order.created_at.date()
        if o_date not in orders_by_date:
            orders_by_date[o_date] = []
        orders_by_date[o_date].append(order)

    # Build sales by day (sorted descending by date)
    sales_by_day = []
    unique_dates = sorted(orders_by_date.keys(), reverse=True)

    grand_subtotal = Decimal("0.00")
    grand_discount = Decimal("0.00")
    grand_tax = Decimal("0.00")
    grand_sales = Decimal("0.00")
    grand_orders_count = len(completed_orders)

    for d in unique_dates:
        d_orders = orders_by_date[d]
        d_count = len(d_orders)
        d_subtotal = sum((o.subtotal for o in d_orders), Decimal("0.00")).quantize(Decimal("0.01"))
        d_discount = sum((o.discount for o in d_orders), Decimal("0.00")).quantize(Decimal("0.01"))
        d_tax = sum((o.tax for o in d_orders), Decimal("0.00")).quantize(Decimal("0.01"))
        d_total = sum((o.total for o in d_orders), Decimal("0.00")).quantize(Decimal("0.01"))
        d_aov = (d_total / Decimal(str(d_count))).quantize(Decimal("0.01")) if d_count > 0 else Decimal("0.00")

        grand_subtotal += d_subtotal
        grand_discount += d_discount
        grand_tax += d_tax
        grand_sales += d_total

        sales_by_day.append({
            "date": d,
            "date_str": d.isoformat(),
            "label": d.strftime("%d %b %Y"),
            "weekday": d.strftime("%A"),
            "orders_count": d_count,
            "subtotal": d_subtotal,
            "discount": d_discount,
            "tax": d_tax,
            "total": d_total,
            "aov": d_aov,
        })

    grand_subtotal = grand_subtotal.quantize(Decimal("0.01"))
    grand_discount = grand_discount.quantize(Decimal("0.01"))
    grand_tax = grand_tax.quantize(Decimal("0.01"))
    grand_sales = grand_sales.quantize(Decimal("0.01"))
    grand_aov = (
        (grand_sales / Decimal(str(grand_orders_count))).quantize(Decimal("0.01"))
        if grand_orders_count > 0
        else Decimal("0.00")
    )

    # 2. Sales by item
    items_qs = (
        OrderItem.objects.filter(
            order__status=Order.Status.COMPLETED,
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=end_date,
        )
        .exclude(status=OrderItem.Status.CANCELLED)
        .values(
            "menu_item__id",
            "menu_item__name",
            "menu_item__category__name",
            "menu_item__price",
        )
        .annotate(
            total_qty=Sum("quantity"),
            total_revenue=Sum(F("quantity") * F("unit_price")),
        )
        .order_by("-total_qty", "-total_revenue")
    )

    sales_by_item = []
    grand_item_qty = 0
    grand_item_revenue = Decimal("0.00")

    for item in items_qs:
        qty = item["total_qty"] or 0
        rev = item["total_revenue"] or Decimal("0.00")
        if not isinstance(rev, Decimal):
            rev = Decimal(str(rev))
        rev = rev.quantize(Decimal("0.01"))
        price = Decimal(str(item["menu_item__price"])).quantize(Decimal("0.01"))

        grand_item_qty += qty
        grand_item_revenue += rev

        sales_by_item.append({
            "id": item["menu_item__id"],
            "name": item["menu_item__name"],
            "category": item["menu_item__category__name"] or "Uncategorized",
            "unit_price": price,
            "quantity": qty,
            "total_revenue": rev,
        })
    grand_item_revenue = grand_item_revenue.quantize(Decimal("0.01"))

    # 3. Sales by payment method
    pm_qs = (
        Payment.objects.filter(
            order__status=Order.Status.COMPLETED,
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=end_date,
        )
        .values("method")
        .annotate(
            total_count=Count("id"),
            total_amount=Sum("amount"),
        )
        .order_by("-total_amount")
    )

    sales_by_payment_method = []
    grand_payment_amount = Decimal("0.00")
    grand_payment_count = 0

    METHOD_LABELS = {
        Payment.Method.CASH: {"name": "Cash", "badge": "success", "icon": "fa-money-bill-wave"},
        Payment.Method.CARD: {"name": "Card", "badge": "primary", "icon": "fa-credit-card"},
        Payment.Method.ONLINE: {"name": "Online", "badge": "info", "icon": "fa-globe"},
    }

    pm_list = list(pm_qs)
    for p in pm_list:
        amt = p["total_amount"] or Decimal("0.00")
        if not isinstance(amt, Decimal):
            amt = Decimal(str(amt))
        grand_payment_amount += amt
        grand_payment_count += p["total_count"] or 0

    grand_payment_amount = grand_payment_amount.quantize(Decimal("0.01"))

    for p in pm_list:
        m_code = p["method"]
        amt = p["total_amount"] or Decimal("0.00")
        if not isinstance(amt, Decimal):
            amt = Decimal(str(amt))
        amt = amt.quantize(Decimal("0.01"))
        cnt = p["total_count"] or 0
        cfg = METHOD_LABELS.get(m_code, {"name": m_code.title(), "badge": "secondary", "icon": "fa-receipt"})

        pct = (
            ((amt / grand_payment_amount) * Decimal("100")).quantize(Decimal("0.1"))
            if grand_payment_amount > Decimal("0.00")
            else Decimal("0.0")
        )

        sales_by_payment_method.append({
            "method": m_code,
            "label": cfg["name"],
            "badge": cfg["badge"],
            "icon": cfg["icon"],
            "count": cnt,
            "total_amount": amt,
            "percentage": pct,
        })

    return {
        "start_date": start_date,
        "end_date": end_date,
        "sales_by_day": sales_by_day,
        "sales_by_item": sales_by_item,
        "sales_by_payment_method": sales_by_payment_method,
        "grand_orders_count": grand_orders_count,
        "grand_subtotal": grand_subtotal,
        "grand_discount": grand_discount,
        "grand_tax": grand_tax,
        "grand_sales": grand_sales,
        "grand_aov": grand_aov,
        "grand_item_qty": grand_item_qty,
        "grand_item_revenue": grand_item_revenue,
        "grand_payment_amount": grand_payment_amount,
        "grand_payment_count": grand_payment_count,
    }


def generate_sales_report_csv(start_date, end_date):
    """
    Generates a CSV string containing all completed orders and line totals
    within the specified date range.
    """
    import csv
    import io
    from django.db.models import Sum

    output = io.StringIO()
    writer = csv.writer(output)

    # 1. Header Information
    setting = Setting.objects.first()
    rest_name = setting.restaurant_name if setting else "Restaurant"
    currency = setting.currency if setting else "PKR"

    writer.writerow([f"{rest_name} - Sales Report"])
    writer.writerow([f"Date Range: {start_date.isoformat()} to {end_date.isoformat()}"])
    writer.writerow([f"Currency: {currency}"])
    writer.writerow([])

    # 2. Orders Table
    writer.writerow([
        "Order ID",
        "Date",
        "Time",
        "Order Type",
        "Table",
        "Waiter",
        "Items Count",
        f"Subtotal ({currency})",
        f"Discount ({currency})",
        "Tax Rate (%)",
        f"Tax ({currency})",
        f"Total Sales ({currency})",
        "Payment Method(s)",
        "Payment Reference(s)",
    ])

    orders = (
        Order.objects.filter(
            status=Order.Status.COMPLETED,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        .select_related("table", "waiter")
        .prefetch_related("items", "payments")
        .order_by("created_at")
    )

    tot_subtotal = Decimal("0.00")
    tot_discount = Decimal("0.00")
    tot_tax = Decimal("0.00")
    tot_sales = Decimal("0.00")
    tot_items_count = 0

    for o in orders:
        items_cnt = o.items.exclude(status=OrderItem.Status.CANCELLED).aggregate(s=Sum("quantity"))["s"] or 0
        tot_items_count += items_cnt
        sub = o.subtotal
        disc = o.discount
        tx = o.tax
        tot = o.total

        tot_subtotal += sub
        tot_discount += disc
        tot_tax += tx
        tot_sales += tot

        pm_methods = ", ".join([p.get_method_display() for p in o.payments.all()]) or "None"
        pm_refs = ", ".join([p.reference for p in o.payments.all() if p.reference]) or "None"

        writer.writerow([
            f"#{o.pk}",
            o.created_at.strftime("%Y-%m-%d"),
            o.created_at.strftime("%H:%M:%S"),
            o.get_order_type_display(),
            o.table.name if o.table else "N/A",
            o.waiter.username if o.waiter else "N/A",
            items_cnt,
            f"{sub:.2f}",
            f"{disc:.2f}",
            f"{o.tax_rate:.2f}",
            f"{tx:.2f}",
            f"{tot:.2f}",
            pm_methods,
            pm_refs,
        ])

    writer.writerow([])
    writer.writerow([
        "TOTALS",
        "",
        "",
        "",
        "",
        f"{orders.count()} orders",
        tot_items_count,
        f"{tot_subtotal:.2f}",
        f"{tot_discount:.2f}",
        "",
        f"{tot_tax:.2f}",
        f"{tot_sales:.2f}",
        "",
        "",
    ])

    return output.getvalue()

