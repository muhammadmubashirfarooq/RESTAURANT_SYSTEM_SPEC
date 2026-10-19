from django.shortcuts import render
from pos.models import Setting


def custom_404_view(request, exception=None):
    """Custom friendly 404 Page Not Found error view."""
    setting = Setting.objects.first()
    return render(request, "pos/404.html", {"setting": setting}, status=404)


def custom_500_view(request):
    """Custom friendly 500 Internal Server Error view."""
    setting = Setting.objects.first()
    return render(request, "pos/500.html", {"setting": setting}, status=500)
