from django.http import HttpResponse
from django.shortcuts import render
from pos.permissions import role_required, get_user_role
from pos.models import Setting
from pos import services


@role_required("Admin", "Manager")
def reports_view(request):
    """
    Phase 6: Comprehensive Sales Reports Page.
    Accessible only by Admin and Manager.
    Includes:
    - Date-range filter (start_date, end_date) with quick presets
    - Summary KPI cards for the selected period
    - Sales by day table
    - Sales by menu item table
    - Sales by payment method breakdown
    - Direct link to CSV export
    """
    setting = Setting.objects.first()
    currency = setting.currency if setting else "PKR"

    start_date_param = request.GET.get("start_date")
    end_date_param = request.GET.get("end_date")

    start_date, end_date = services.parse_date_range(start_date_param, end_date_param, default_days=30)
    report_data = services.get_reports_data(start_date, end_date)

    context = {
        "title": "Sales Reports & Analytics",
        "role": get_user_role(request.user),
        "setting": setting,
        "currency": currency,
        "report": report_data,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }

    return render(request, "pos/reports/index.html", context)


@role_required("Admin", "Manager")
def reports_export_csv_view(request):
    """
    Phase 6: CSV Export of sales data at /reports/export.csv.
    Accessible only by Admin and Manager.
    Filters completed orders by date-range (start_date, end_date).
    """
    start_date_param = request.GET.get("start_date")
    end_date_param = request.GET.get("end_date")

    start_date, end_date = services.parse_date_range(start_date_param, end_date_param, default_days=30)
    csv_content = services.generate_sales_report_csv(start_date, end_date)

    filename = f"sales_report_{start_date.isoformat()}_to_{end_date.isoformat()}.csv"
    response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
