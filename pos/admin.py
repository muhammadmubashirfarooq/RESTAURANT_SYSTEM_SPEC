from django.contrib import admin
from .models import Category, MenuItem, DiningTable, Order, OrderItem, Payment, Setting


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "sort_order")
    list_editable = ("sort_order",)
    search_fields = ("name",)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "category", "price", "is_available")
    list_filter = ("category", "is_available")
    search_fields = ("name", "description")
    list_editable = ("price", "is_available")


@admin.register(DiningTable)
class DiningTableAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "capacity", "status")
    list_filter = ("status",)
    search_fields = ("name",)
    list_editable = ("status",)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "waiter", "status", "order_type", "created_at", "closed_at")
    list_filter = ("status", "order_type", "created_at")
    search_fields = ("id", "notes", "table__name", "waiter__username")
    inlines = [OrderItemInline, PaymentInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "menu_item", "quantity", "unit_price", "status")
    list_filter = ("status",)
    search_fields = ("menu_item__name", "order__id")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "cashier", "method", "amount", "paid_at")
    list_filter = ("method", "paid_at")
    search_fields = ("order__id", "reference")


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ("restaurant_name", "phone", "tax_rate", "currency")
