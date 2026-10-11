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
