from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import F, Sum


class Category(models.Model):
    name = models.CharField(max_length=80)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="menu/", blank=True, null=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.price})"


class DiningTable(models.Model):
    class Status(models.TextChoices):
        FREE = "free", "Free"
        OCCUPIED = "occupied", "Occupied"
        RESERVED = "reserved", "Reserved"

    name = models.CharField(max_length=30, unique=True)  # e.g., T1, T2, VIP-1
    capacity = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.FREE)

    def __str__(self):
        return self.name


class Order(models.Model):
    class Type(models.TextChoices):
        DINE_IN = "dine_in", "Dine in"
        TAKEAWAY = "takeaway", "Takeaway"
        DELIVERY = "delivery", "Delivery"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready"
        SERVED = "served", "Served"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    order_type = models.CharField(max_length=10, choices=Type.choices, default=Type.DINE_IN)
    table = models.ForeignKey(DiningTable, null=True, blank=True, on_delete=models.SET_NULL)
    waiter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # percent
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk}"

    @property
    def subtotal(self):
        total = self.items.exclude(status="cancelled").aggregate(
            t=Sum(F("quantity") * F("unit_price"))
        )["t"]
        return total or Decimal("0")

    @property
    def tax(self):
        return ((self.subtotal - self.discount) * self.tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def total(self):
        return self.subtotal - self.discount + self.tax

    @property
    def paid_amount(self):
        return self.payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    @property
    def is_paid(self):
        return self.paid_amount >= self.total


class OrderItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready"
        SERVED = "served", "Served"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)  # price at order time
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=200, blank=True)

    def save(self, *args, **kwargs):
        if not self.unit_price:
            self.unit_price = self.menu_item.price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name}"


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        ONLINE = "online", "Online"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    method = models.CharField(max_length=10, choices=Method.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    paid_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment #{self.pk} - PKR {self.amount} ({self.method})"


class Setting(models.Model):
    restaurant_name = models.CharField(max_length=120, default="My Restaurant")
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="PKR")

    def __str__(self):
        return self.restaurant_name
