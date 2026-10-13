from decimal import Decimal
from django.urls import reverse
from django.db import transaction
from .models import DiningTable, Order, OrderItem, MenuItem, Setting
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
def cancel_order(order):
    """
    Cancels an order and frees the table.
    Rule: A cancelled order frees the table.
    """
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status"])

    # Cancel all items
    order.items.update(status=OrderItem.Status.CANCELLED)

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
