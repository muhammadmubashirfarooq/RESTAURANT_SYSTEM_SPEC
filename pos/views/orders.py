from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from pos.permissions import role_required, get_user_role
from pos.models import Category, DiningTable, MenuItem, Order, Setting
from pos import services


@role_required("Admin", "Manager", "Waiter")
def order_create_view(request, table_id):
    """
    Creates a new order for a dining table or redirects to existing active order.
    """
    table = get_object_or_404(DiningTable, pk=table_id)
    active_order = services.get_active_order_for_table(table)

    if active_order:
        messages.info(request, f"Table {table.name} already has an active order (#{active_order.pk}).")
        return redirect("order_detail", order_id=active_order.pk)

    order = services.create_order(table=table, waiter=request.user)
    messages.success(request, f"New order started for Table {table.name}.")
    return redirect("order_detail", order_id=order.pk)


@role_required("Admin", "Manager", "Waiter")
def order_detail_view(request, order_id):
    """
    Order screen for waiter:
    - Left side: menu with category tabs and search
    - Right side: live cart with quantity +/-, notes, subtotal, send/cancel actions.
    """
    order = get_object_or_404(
        Order.objects.select_related("table", "waiter").prefetch_related("items__menu_item"),
        pk=order_id,
    )
    categories = Category.objects.all().order_by("sort_order", "name")
    menu_items = MenuItem.objects.select_related("category").all().order_by("category__sort_order", "name")
    setting = Setting.objects.first()

    context = {
        "title": f"Order #{order.pk} - Table {order.table.name if order.table else 'Takeaway'}",
        "role": get_user_role(request.user),
        "order": order,
        "categories": categories,
        "menu_items": menu_items,
        "setting": setting,
    }
    return render(request, "pos/orders/detail.html", context)


@role_required("Admin", "Manager", "Waiter")
def order_cart_view(request, order_id):
    """
    HTMX GET view to refresh order cart fragment with live item statuses.
    """
    order = get_object_or_404(
        Order.objects.select_related("table", "waiter").prefetch_related("items__menu_item"),
        pk=order_id,
    )
    setting = Setting.objects.first()
    return render(request, "pos/orders/cart_partial.html", {"order": order, "setting": setting})


@role_required("Admin", "Manager", "Waiter")
def order_add_item_view(request, order_id):
    """
    HTMX POST view to add a menu item to the order cart.
    """
    order = get_object_or_404(Order, pk=order_id)
    if request.method == "POST":
        menu_item_id = request.POST.get("menu_item_id")
        try:
            quantity = int(request.POST.get("quantity", 1))
        except (ValueError, TypeError):
            quantity = 1
        note = request.POST.get("note", "")

        try:
            services.add_item_to_order(order, menu_item_id, quantity=quantity, note=note)
        except ValueError as e:
            messages.error(request, str(e))

    if request.headers.get("HX-Request"):
        setting = Setting.objects.first()
        return render(request, "pos/orders/cart_partial.html", {"order": order, "setting": setting})

    return redirect("order_detail", order_id=order.pk)


@role_required("Admin", "Manager", "Waiter")
def order_update_item_view(request, order_id, item_id):
    """
    HTMX POST view to update item quantity (+/-) or note.
    """
    order = get_object_or_404(Order, pk=order_id)
    if request.method == "POST":
        delta = request.POST.get("delta")
        new_quantity = request.POST.get("quantity")
        note = request.POST.get("note")

        if delta is not None:
            try:
                services.update_order_item_quantity(order, item_id, delta=int(delta))
            except (ValueError, TypeError):
                pass
        elif new_quantity is not None:
            try:
                services.update_order_item_quantity(order, item_id, new_quantity=int(new_quantity))
            except (ValueError, TypeError):
                pass

        if note is not None:
            services.update_order_item_note(order, item_id, note)

    if request.headers.get("HX-Request"):
        setting = Setting.objects.first()
        return render(request, "pos/orders/cart_partial.html", {"order": order, "setting": setting})

    return redirect("order_detail", order_id=order.pk)


@role_required("Admin", "Manager", "Waiter")
def order_remove_item_view(request, order_id, item_id):
    """
    Removes an item from the order cart.
    """
    order = get_object_or_404(Order, pk=order_id)
    if request.method in ["POST", "GET"]:
        services.remove_order_item(order, item_id)

    if request.headers.get("HX-Request"):
        setting = Setting.objects.first()
        return render(request, "pos/orders/cart_partial.html", {"order": order, "setting": setting})

    return redirect("order_detail", order_id=order.pk)


@role_required("Admin", "Manager", "Waiter")
def order_send_view(request, order_id):
    """
    Sends order to kitchen and redirects back to tables view.
    Rule: Table remains / turns occupied (red).
    """
    order = get_object_or_404(Order, pk=order_id)
    if request.method == "POST":
        try:
            services.send_order_to_kitchen(order)
            messages.success(request, f"Order #{order.pk} sent to kitchen successfully!")
            return redirect("tables")
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("order_detail", order_id=order.pk)

    return redirect("order_detail", order_id=order.pk)


@role_required("Admin", "Manager", "Waiter")
def order_cancel_view(request, order_id):
    """
    Cancels order and frees table (turns green).
    """
    order = get_object_or_404(Order, pk=order_id)
    if request.method == "POST":
        table_name = order.table.name if order.table else "N/A"
        services.cancel_order(order)
        messages.warning(request, f"Order #{order.pk} cancelled. Table {table_name} is now free.")
        return redirect("tables")

    return redirect("order_detail", order_id=order.pk)
