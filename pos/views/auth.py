from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from pos.services import get_role_redirect_url


def login_view(request):
    if request.user.is_authenticated:
        return redirect(get_role_redirect_url(request.user))

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            next_url = request.GET.get("next")
            if next_url:
                return redirect(next_url)
            return redirect(get_role_redirect_url(user))
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "pos/login.html")


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")


@login_required
def home_redirect(request):
    return redirect(get_role_redirect_url(request.user))
