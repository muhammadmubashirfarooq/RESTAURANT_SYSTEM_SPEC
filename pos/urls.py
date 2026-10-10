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
]
