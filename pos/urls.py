from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_redirect, name="home_redirect"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("tables/", views.tables_view, name="tables"),
    path("kitchen/", views.kitchen_view, name="kitchen"),
    path("billing/", views.billing_view, name="billing"),

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
]
