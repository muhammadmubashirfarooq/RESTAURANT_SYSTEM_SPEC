from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from decimal import Decimal, InvalidOperation

from pos.models import Order, Payment, Setting
from pos.permissions import role_required, get_user_role
from pos import services


@role_required("Admin", "Manager", "Cashier")
def billing_list_view(request):
    """
    Billing list for Cashier (also Manager/Admin): open orders with totals (Section 4 & 10).
    """
    open_orders = services.get_billing_orders()
    setting = Setting.objects.first()

    # Pre-calculate summary statistics
    total_open_amount = sum((order.total for order in open_orders), Decimal("0.00"))
    ready_orders_count = sum(1 for order in open_orders if order.status in ["ready", "served"])

    # Recent completed orders for convenience/receipt reprinting
    recent_completed = (
        Order.objects.filter(status=Order.Status.COMPLETED)
        .select_related("table", "waiter")
        .prefetch_related("payments")
        .order_by("-closed_at")[:8]
    )

    context = {
        "title": "Billing & Cashier Terminal",
        "role": get_user_role(request.user),
        "setting": setting,
        "open_orders": open_orders,
        "total_open_count": open_orders.count(),
        "ready_orders_count": ready_orders_count,
        "total_open_amount": total_open_amount,
        "recent_completed": recent_completed,
    }
    return render(request, "pos/billing/list.html", context)


@role_required("Admin", "Manager", "Cashier")
def billing_detail_view(request, order_id):
    """
    Bill screen: item list, discount input, tax (rate from Settings), total,
    payment method (cash / card / online), amount received, change due.
    Split payments are allowed (several Payment rows per order).
    """
    order = get_object_or_404(
        Order.objects.select_related("table", "waiter").prefetch_related("items__menu_item", "payments__cashier"),
        pk=order_id,
    )
    setting = Setting.objects.first()
    active_items = order.items.exclude(status="cancelled")
    payments = order.payments.all().order_by("paid_at")

    context = {
        "title": f"Bill for Order #{order.pk}",
        "role": get_user_role(request.user),
        "order": order,
        "setting": setting,
        "items": active_items,
        "payments": payments,
        "payment_methods": Payment.Method.choices,
    }
    return render(request, "pos/billing/detail.html", context)


@role_required("Admin", "Manager", "Cashier")
def billing_discount_view(request, order_id):
    """
    Applies discount to order with server-side validation:
    Rule: Discount cannot be negative or more than the subtotal.
    """
    if request.method != "POST":
        return redirect("billing_detail", order_id=order_id)

    order = get_object_or_404(Order, pk=order_id)
    discount_input = request.POST.get("discount", "0").strip()

    try:
        discount_val = Decimal(discount_input)
        services.apply_order_discount(order, discount_val)
        messages.success(request, f"Discount of {discount_val:.2f} applied successfully.")
    except (ValueError, InvalidOperation) as e:
        messages.error(request, f"Failed to apply discount: {str(e)}")

    return redirect("billing_detail", order_id=order.pk)


@role_required("Admin", "Manager", "Cashier")
def billing_pay_view(request, order_id):
    """
    Takes payment for an order.
    Rules:
    - Cancelled order cannot be paid.
    - Payment amount must be greater than zero.
    - Split payments allowed.
    - When paid amount >= total: order becomes completed, closed_at set, table freed.
    """
    if request.method != "POST":
        return redirect("billing_detail", order_id=order_id)

    order = get_object_or_404(Order, pk=order_id)
    setting = Setting.objects.first()
    currency = setting.currency if setting else "PKR"

    method = request.POST.get("method", Payment.Method.CASH)
    amount_str = request.POST.get("amount", "").strip()
    tendered_str = request.POST.get("tendered", "").strip() or None
    reference = request.POST.get("reference", "").strip()

    try:
        payment, change_due, is_completed = services.record_payment(
            order=order,
            cashier=request.user,
            method=method,
            amount=amount_str,
            reference=reference,
            tendered=tendered_str,
        )

        if is_completed:
            table_str = f"Table {order.table.name}" if order.table else "Table N/A"
            msg = f"Order #{order.pk} is now fully paid and completed! {table_str} has been freed."
            if change_due > Decimal("0.00"):
                msg += f" Change Due: {currency} {change_due:.2f}"
            messages.success(request, msg)
        else:
            msg = f"Payment of {currency} {payment.amount:.2f} recorded via {payment.get_method_display()}."
            if change_due > Decimal("0.00"):
                msg += f" Change Due: {currency} {change_due:.2f}."
            msg += f" Remaining Balance: {currency} {order.remaining_balance:.2f}."
            messages.info(request, msg)

    except (ValueError, InvalidOperation) as e:
        messages.error(request, f"Payment failed: {str(e)}")

    return redirect("billing_detail", order_id=order.pk)


@role_required("Admin", "Manager", "Cashier")
def billing_receipt_pdf_view(request, order_id):
    """
    PDF receipt download at /billing/<order_id>/receipt.pdf
    Includes restaurant name, address, phone, items, tax, discount, total, payment method, date, order no.
    Uses xhtml2pdf (pure Python).
    """
    order = get_object_or_404(Order, pk=order_id)
    pdf_bytes = services.generate_receipt_pdf(order)

    if not pdf_bytes:
        raise Http404("Could not generate PDF receipt.")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="receipt_order_{order.pk}.pdf"'
    return response
