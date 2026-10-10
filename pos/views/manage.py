from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from pos.forms import CategoryForm, DiningTableForm, MenuItemForm
from pos.models import Category, DiningTable, MenuItem
from pos.permissions import role_required


# --- CATEGORIES ---

@role_required("Admin", "Manager")
def category_list_view(request):
    categories = Category.objects.all()
    form = CategoryForm()
    return render(
        request,
        "pos/manage/categories.html",
        {
            "categories": categories,
            "form": form,
        },
    )


@role_required("Admin", "Manager")
def category_save_view(request, category_id=None):
    category = get_object_or_404(Category, pk=category_id) if category_id else None
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{form.cleaned_data['name']}' saved successfully.")
        else:
            messages.error(request, "Failed to save category. Please check errors.")
    return redirect("manage_categories")


@role_required("Admin", "Manager")
def category_delete_view(request, category_id):
    category = get_object_or_404(Category, pk=category_id)
    if request.method == "POST":
        if category.items.exists():
            messages.error(request, f"Cannot delete category '{category.name}' because it contains menu items.")
        else:
            name = category.name
            category.delete()
            messages.success(request, f"Category '{name}' deleted successfully.")
    return redirect("manage_categories")


# --- MENU ITEMS ---

@role_required("Admin", "Manager")
def menu_list_view(request):
    category_id = request.GET.get("category")
    search_query = request.GET.get("q", "").strip()

    items = MenuItem.objects.select_related("category").all()
    if category_id:
        items = items.filter(category_id=category_id)
    if search_query:
        items = items.filter(name__icontains=search_query)

    categories = Category.objects.all()
    form = MenuItemForm()

    return render(
        request,
        "pos/manage/menu.html",
        {
            "items": items,
            "categories": categories,
            "selected_category": int(category_id) if category_id and category_id.isdigit() else None,
            "search_query": search_query,
            "form": form,
        },
    )


@role_required("Admin", "Manager")
def menu_save_view(request, item_id=None):
    item = get_object_or_404(MenuItem, pk=item_id) if item_id else None
    if request.method == "POST":
        form = MenuItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            saved_item = form.save()
            messages.success(request, f"Menu item '{saved_item.name}' saved successfully.")
        else:
            messages.error(request, "Failed to save menu item. Please check errors.")
    return redirect("manage_menu")


@role_required("Admin", "Manager")
def menu_delete_view(request, item_id):
    item = get_object_or_404(MenuItem, pk=item_id)
    if request.method == "POST":
        name = item.name
        item.delete()
        messages.success(request, f"Menu item '{name}' deleted successfully.")
    return redirect("manage_menu")


@role_required("Admin", "Manager")
def menu_toggle_availability_view(request, item_id):
    item = get_object_or_404(MenuItem, pk=item_id)
    if request.method == "POST":
        item.is_available = not item.is_available
        item.save()
        status_text = "Available" if item.is_available else "Unavailable"
        messages.success(request, f"'{item.name}' is now marked as {status_text}.")

        # If request comes from HTMX, return a component partial or fragment if desired,
        # otherwise redirect to manage_menu.
        if request.headers.get("HX-Request"):
            badge_class = "bg-success" if item.is_available else "bg-secondary"
            btn_class = "btn-warning" if item.is_available else "btn-success"
            action_text = "Make Unavailable" if item.is_available else "Make Available"
            html = f"""
            <div id="item-avail-{item.pk}">
                <span class="badge {badge_class} mb-2">{"Available" if item.is_available else "Unavailable"}</span>
                <form method="post" action="{reverse('manage_menu_toggle', kwargs={'item_id': item.pk})}" hx-post="{reverse('manage_menu_toggle', kwargs={'item_id': item.pk})}" hx-target="#item-avail-{item.pk}" hx-swap="outerHTML">
                    <input type="hidden" name="csrfmiddlewaretoken" value="{request.META.get('CSRF_COOKIE', '')}">
                    <button type="submit" class="btn btn-sm {btn_class} w-100">
                        <i class="fa-solid fa-power-off me-1"></i> {action_text}
                    </button>
                </form>
            </div>
            """
            return HttpResponse(html)

    return redirect("manage_menu")


# --- TABLES ---

@role_required("Admin", "Manager")
def table_manage_list_view(request):
    tables = DiningTable.objects.all().order_by("name")
    form = DiningTableForm()
    return render(
        request,
        "pos/manage/tables.html",
        {
            "tables": tables,
            "form": form,
        },
    )


@role_required("Admin", "Manager")
def table_manage_save_view(request, table_id=None):
    table = get_object_or_404(DiningTable, pk=table_id) if table_id else None
    if request.method == "POST":
        form = DiningTableForm(request.POST, instance=table)
        if form.is_valid():
            saved_table = form.save()
            messages.success(request, f"Table '{saved_table.name}' saved successfully.")
        else:
            messages.error(request, "Failed to save table. Please check errors.")
    return redirect("manage_tables")


@role_required("Admin", "Manager")
def table_manage_delete_view(request, table_id):
    table = get_object_or_404(DiningTable, pk=table_id)
    if request.method == "POST":
        name = table.name
        table.delete()
        messages.success(request, f"Table '{name}' deleted successfully.")
    return redirect("manage_tables")
