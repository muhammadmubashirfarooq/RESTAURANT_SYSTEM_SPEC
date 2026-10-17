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
