from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_redirect, name="home_redirect"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("tables/", views.tables_view, name="tables"),
    path("kitchen/", views.kitchen_board_view, name="kitchen"),
    path("kitchen/partial/", views.kitchen_partial_view, name="kitchen_partial"),
    path("kitchen/item/<int:item_id>/status/", views.kitchen_item_status_view, name="kitchen_item_status"),
    path("kitchen/order/<int:order_id>/batch-status/", views.kitchen_order_batch_status_view, name="kitchen_order_batch_status"),
    path("billing/", views.billing_list_view, name="billing"),
    path("billing/<int:order_id>/", views.billing_detail_view, name="billing_detail"),
    path("billing/<int:order_id>/discount/", views.billing_discount_view, name="billing_discount"),
    path("billing/<int:order_id>/pay/", views.billing_pay_view, name="billing_pay"),
    path("billing/<int:order_id>/receipt.pdf", views.billing_receipt_pdf_view, name="billing_receipt_pdf"),

    # Phase 3: Order Taking
    path("orders/new/<int:table_id>/", views.order_create_view, name="order_new"),
    path("orders/<int:order_id>/", views.order_detail_view, name="order_detail"),
    path("orders/<int:order_id>/cart/", views.order_cart_view, name="order_cart"),
    path("orders/<int:order_id>/add-item/", views.order_add_item_view, name="order_add_item"),
    path("orders/<int:order_id>/update-item/<int:item_id>/", views.order_update_item_view, name="order_update_item"),
    path("orders/<int:order_id>/remove-item/<int:item_id>/", views.order_remove_item_view, name="order_remove_item"),
    path("orders/<int:order_id>/send/", views.order_send_view, name="order_send"),
    path("orders/<int:order_id>/cancel/", views.order_cancel_view, name="order_cancel"),

    # Category Management
    path("manage/categories/", views.category_list_view, name="manage_categories"),
    path("manage/categories/save/", views.category_save_view, name="manage_categories_save"),
    path("manage/categories/<int:category_id>/save/", views.category_save_view, name="manage_categories_edit"),
    path("manage/categories/<int:category_id>/delete/", views.category_delete_view, name="manage_categories_delete"),

    # Menu Management
    path("manage/menu/", views.menu_list_view, name="manage_menu"),
    path("manage/menu/save/", views.menu_save_view, name="manage_menu_save"),
    path("manage/menu/<int:item_id>/save/", views.menu_save_view, name="manage_menu_edit"),
    path("manage/menu/<int:item_id>/delete/", views.menu_delete_view, name="manage_menu_delete"),
    path("manage/menu/<int:item_id>/toggle/", views.menu_toggle_availability_view, name="manage_menu_toggle"),

    # Table Management
    path("manage/tables/", views.table_manage_list_view, name="manage_tables"),
    path("manage/tables/save/", views.table_manage_save_view, name="manage_tables_save"),
    path("manage/tables/<int:table_id>/save/", views.table_manage_save_view, name="manage_tables_edit"),
    path("manage/tables/<int:table_id>/delete/", views.table_manage_delete_view, name="manage_tables_delete"),

    # Settings
    path("settings/", views.settings_view, name="settings"),

    # Phase 6: Reports & Analytics
    path("reports/", views.reports_view, name="reports"),
    path("reports/export.csv", views.reports_export_csv_view, name="reports_export_csv"),
]

