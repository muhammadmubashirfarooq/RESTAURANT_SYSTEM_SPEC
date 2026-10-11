from django.shortcuts import render
from pos.permissions import role_required, get_user_role
from pos.models import DiningTable, Setting
from pos.services import get_active_order_for_table


@role_required("Admin", "Manager", "Waiter")
def tables_view(request):
    """
    Displays the tables grid for waiters and managers.
    Tables are colored by status:
    - Free: Green (starts a new order on click)
    - Occupied: Red (opens active order on click)
    - Reserved: Orange
    """
    tables = DiningTable.objects.all().order_by("name")
    setting = Setting.objects.first()

    # Attach active order to each table
    table_list = []
    total_count = len(tables)
    free_count = 0
    occupied_count = 0
    reserved_count = 0

    for table in tables:
        active_order = get_active_order_for_table(table)
        if table.status == DiningTable.Status.FREE:
            free_count += 1
        elif table.status == DiningTable.Status.OCCUPIED:
            occupied_count += 1
        elif table.status == DiningTable.Status.RESERVED:
            reserved_count += 1

        table_list.append({
            "table": table,
            "active_order": active_order,
        })

    context = {
        "title": "Dining Tables",
        "role": get_user_role(request.user),
        "setting": setting,
        "table_list": table_list,
        "stats": {
            "total": total_count,
            "free": free_count,
            "occupied": occupied_count,
            "reserved": reserved_count,
        },
    }
    return render(request, "pos/tables.html", context)
