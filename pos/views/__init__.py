from .auth import login_view, logout_view, home_redirect
from .placeholder import dashboard_view, tables_view, kitchen_view, billing_view
from .manage import (
    category_list_view,
    category_save_view,
    category_delete_view,
    menu_list_view,
    menu_save_view,
    menu_delete_view,
    menu_toggle_availability_view,
    table_manage_list_view,
    table_manage_save_view,
    table_manage_delete_view,
)
from .settings import settings_view
