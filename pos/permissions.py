from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="Admin").exists())


def is_manager(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name__in=["Admin", "Manager"]).exists()
    )


def is_waiter(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name__in=["Admin", "Manager", "Waiter"]).exists()
    )


def is_kitchen(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name__in=["Admin", "Manager", "Kitchen"]).exists()
    )


def is_cashier(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name__in=["Admin", "Manager", "Cashier"]).exists()
    )


def role_required(*allowed_roles):
    """
    Decorator for views that checks whether a user has at least one of the allowed roles.
    Allowed roles can be 'Admin', 'Manager', 'Waiter', 'Kitchen', 'Cashier'.
    Superusers bypass all role checks.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            user_groups = set(request.user.groups.values_list("name", flat=True))
            if any(role in user_groups for role in allowed_roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("You do not have permission to access this page.")
        return _wrapped_view
    return decorator


def get_user_role(user):
    """Return primary role string for navbar/redirection."""
    if not user.is_authenticated:
        return None
    if user.is_superuser or user.groups.filter(name="Admin").exists():
        return "Admin"
    if user.groups.filter(name="Manager").exists():
        return "Manager"
    if user.groups.filter(name="Waiter").exists():
        return "Waiter"
    if user.groups.filter(name="Kitchen").exists():
        return "Kitchen"
    if user.groups.filter(name="Cashier").exists():
        return "Cashier"
    return "Staff"
