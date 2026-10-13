from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from pos.models import Order, OrderItem, Setting
from pos.permissions import role_required, get_user_role
from pos import services


@role_required("Admin", "Manager", "Kitchen")
def kitchen_board_view(request):
    """
    Main Kitchen Display System (KDS) board view.
    Displays orders in 3 columns: Pending / Preparing / Ready.
    Refreshes automatically via HTMX every 5 seconds.
    """
    data = services.get_kitchen_board_data()
    context = {
        "title": "Kitchen Display System",
        "role": get_user_role(request.user),
        **data,
    }
    return render(request, "pos/kitchen/board.html", context)


@role_required("Admin", "Manager", "Kitchen")
def kitchen_partial_view(request):
    """
    HTMX partial fragment endpoint for 5-second polling of the kitchen board.
    """
    data = services.get_kitchen_board_data()
    context = {
        **data,
    }
    return render(request, "pos/kitchen/board_partial.html", context)


def kitchen_item_status_view(request, item_id):
    """
    HTMX POST endpoint to move an item through its lifecycle:
    pending -> preparing -> ready -> served.
    Server checks roles:
    - Kitchen, Manager, Admin can change to 'preparing' or 'ready'.
    - Waiter, Kitchen, Manager, Admin can mark ready items as 'served'.
    """
    if not request.user.is_authenticated:
        return redirect("login")

    order_item = get_object_or_404(OrderItem.objects.select_related("order"), pk=item_id)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status:
            try:
                services.update_order_item_status(order_item, new_status, request.user)
            except PermissionDenied as e:
                raise e
            except Exception as e:
                messages.error(request, str(e))

    # Respond with updated fragment depending on caller
    hx_target = request.headers.get("HX-Target", "")
    source = request.POST.get("source", "")
    referer = request.META.get("HTTP_REFERER", "")

    if hx_target == "order-cart" or source == "order" or "/orders/" in referer:
        setting = Setting.objects.first()
        return render(
            request,
            "pos/orders/cart_partial.html",
            {"order": order_item.order, "setting": setting},
        )

    if request.headers.get("HX-Request"):
        data = services.get_kitchen_board_data()
        return render(request, "pos/kitchen/board_partial.html", data)

    return redirect("kitchen")


@role_required("Admin", "Manager", "Kitchen")
def kitchen_order_batch_status_view(request, order_id):
    """
    HTMX POST endpoint to transition all active items of an order at once
    (e.g., 'Start All Items' or 'Mark All Ready').
    """
    order = get_object_or_404(Order, pk=order_id)
    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status:
            services.update_order_all_items_status(order, new_status, request.user)

    if request.headers.get("HX-Request"):
        data = services.get_kitchen_board_data()
        return render(request, "pos/kitchen/board_partial.html", data)

    return redirect("kitchen")
