from django.shortcuts import render
from pos.permissions import role_required, get_user_role
from pos.models import MenuItem, DiningTable, Order, Setting


@role_required("Admin", "Manager")
def dashboard_view(request):
    setting = Setting.objects.first()
    context = {
        "title": "Sales Dashboard",
        "role": get_user_role(request.user),
        "setting": setting,
        "total_orders": Order.objects.count(),
        "total_tables": DiningTable.objects.count(),
        "total_menu_items": MenuItem.objects.count(),
    }
    return render(request, "pos/placeholder.html", context)
