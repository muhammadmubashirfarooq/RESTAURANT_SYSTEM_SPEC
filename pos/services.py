from django.urls import reverse
from .permissions import get_user_role


def get_role_redirect_url(user):
    """
    Role-based redirect URLs after login (Section 3):
    Admin/Manager -> Dashboard (/dashboard/)
    Waiter -> Tables (/tables/)
    Kitchen -> Kitchen screen (/kitchen/)
    Cashier -> Billing list (/billing/)
    """
    role = get_user_role(user)
    if role in ["Admin", "Manager"]:
        return reverse("dashboard")
    elif role == "Waiter":
        return reverse("tables")
    elif role == "Kitchen":
        return reverse("kitchen")
    elif role == "Cashier":
        return reverse("billing")
    return reverse("dashboard")
