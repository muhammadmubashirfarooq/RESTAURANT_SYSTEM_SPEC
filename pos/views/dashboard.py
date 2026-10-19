import json
from decimal import Decimal
from django.shortcuts import render
from pos.permissions import role_required, get_user_role
from pos.models import Setting
from pos import services


@role_required("Admin", "Manager")
def dashboard_view(request):
    """
    Phase 6: Sales & Operations Dashboard for Admin and Manager.
    Displays:
    - KPI Cards: Today's Sales, Orders Count, Average Order Value (AOV), and Lifetime Stats
    - Top 5 Best-Selling Items with revenue and quantities
    - Last 7 Days Sales Trend Line Chart (Chart.js)
    - Orders by Status Breakdown Doughnut Chart (Chart.js)
    """
    setting = Setting.objects.first()
    currency = setting.currency if setting else "PKR"

    # 1. KPI Metrics
    metrics = services.get_dashboard_metrics()

    # 2. Top 5 Items
    top_items = services.get_dashboard_top_items(limit=5)

    # 3. Last 7 Days Sales Trend
    sales_trend = services.get_dashboard_sales_trend(days=7)
    trend_labels = [item["label"] for item in sales_trend]
    trend_values = [item["sales_float"] for item in sales_trend]
    trend_orders = [item["orders_count"] for item in sales_trend]

    # 4. Orders by Status
    status_breakdown = services.get_dashboard_orders_by_status()
    status_labels = [item["label"] for item in status_breakdown]
    status_values = [item["count"] for item in status_breakdown]
    status_colors = [item["color"] for item in status_breakdown]
    status_borders = [item["border"] for item in status_breakdown]

    context = {
        "title": "Sales Dashboard",
        "role": get_user_role(request.user),
        "setting": setting,
        "currency": currency,
        "metrics": metrics,
        "top_items": top_items,
        "sales_trend": sales_trend,
        "status_breakdown": status_breakdown,
        # JSON serialized data for Chart.js
        "trend_labels_json": json.dumps(trend_labels),
        "trend_values_json": json.dumps(trend_values),
        "trend_orders_json": json.dumps(trend_orders),
        "status_labels_json": json.dumps(status_labels),
        "status_values_json": json.dumps(status_values),
        "status_colors_json": json.dumps(status_colors),
        "status_borders_json": json.dumps(status_borders),
    }

    return render(request, "pos/dashboard.html", context)
