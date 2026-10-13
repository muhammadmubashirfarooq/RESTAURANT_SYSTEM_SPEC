from .auth import login_view, logout_view, home_redirect
from .placeholder import dashboard_view, billing_view
from .tables import tables_view
from .kitchen import (
    kitchen_board_view,
    kitchen_partial_view,
    kitchen_item_status_view,
    kitchen_order_batch_status_view,
)
from .orders import (
    order_create_view,
    order_detail_view,
    order_cart_view,
    order_add_item_view,
    order_update_item_view,
    order_remove_item_view,
    order_send_view,
    order_cancel_view,
)
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
