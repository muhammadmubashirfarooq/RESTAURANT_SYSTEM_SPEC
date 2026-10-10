from decimal import Decimal
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from pos.models import Category, DiningTable, MenuItem, Setting


class Phase2ManagementTests(TestCase):
    def setUp(self):
        call_command("seed_demo")
        self.manager = User.objects.get(username="manager")
        self.waiter = User.objects.get(username="waiter")
        self.client.login(username="manager", password="demo123")

    # --- CATEGORY TESTS ---

    def test_category_list_access(self):
        response = self.client.get(reverse("manage_categories"))
        self.assertEqual(response.status_code, 200)

    def test_category_create_and_edit(self):
        # Create category
        response = self.client.post(
            reverse("manage_categories_save"),
            {"name": "Mocktails & Smoothies", "sort_order": 99},
            follow=True,
        )
        self.assertRedirects(response, reverse("manage_categories"))
        new_cat = Category.objects.get(name="Mocktails & Smoothies")
        self.assertEqual(new_cat.sort_order, 99)

        # Edit category
        response_edit = self.client.post(
            reverse("manage_categories_edit", kwargs={"category_id": new_cat.pk}),
            {"name": "Sweet Mocktails", "sort_order": 100},
            follow=True,
        )
        new_cat.refresh_from_db()
        self.assertEqual(new_cat.name, "Sweet Mocktails")
        self.assertEqual(new_cat.sort_order, 100)

    def test_category_delete(self):
        empty_cat = Category.objects.create(name="Empty Category", sort_order=50)
        response = self.client.post(
            reverse("manage_categories_delete", kwargs={"category_id": empty_cat.pk}),
            follow=True,
        )
        self.assertFalse(Category.objects.filter(pk=empty_cat.pk).exists())

        # Cannot delete category with items
        cat_with_items = Category.objects.first()
        response_blocked = self.client.post(
            reverse("manage_categories_delete", kwargs={"category_id": cat_with_items.pk}),
            follow=True,
        )
        self.assertTrue(Category.objects.filter(pk=cat_with_items.pk).exists())

    # --- MENU ITEM TESTS ---

    def test_menu_list_access(self):
        response = self.client.get(reverse("manage_menu"))
        self.assertEqual(response.status_code, 200)

    def test_menu_item_create_with_image_and_toggle(self):
        cat = Category.objects.first()
        # 1x1 GIF image bytes
        image_content = (
            b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff"
            b"\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
            b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
        )
        test_image = SimpleUploadedFile("test_food.gif", image_content, content_type="image/gif")

        response = self.client.post(
            reverse("manage_menu_save"),
            {
                "category": cat.pk,
                "name": "Special Mango Lassi",
                "description": "Fresh mango smoothie with yogurt",
                "price": "350.00",
                "image": test_image,
                "is_available": "on",
            },
            follow=True,
        )
        self.assertRedirects(response, reverse("manage_menu"))

        item = MenuItem.objects.get(name="Special Mango Lassi")
        self.assertEqual(item.price, Decimal("350.00"))
        self.assertTrue(item.is_available)
        self.assertTrue(bool(item.image))

        # Toggle availability via standard POST
        toggle_response = self.client.post(
            reverse("manage_menu_toggle", kwargs={"item_id": item.pk}),
            follow=True,
        )
        item.refresh_from_db()
        self.assertFalse(item.is_available)

        # Toggle back via HTMX request
        htmx_response = self.client.post(
            reverse("manage_menu_toggle", kwargs={"item_id": item.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(htmx_response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_available)

    def test_menu_item_negative_price_validation(self):
        cat = Category.objects.first()
        response = self.client.post(
            reverse("manage_menu_save"),
            {
                "category": cat.pk,
                "name": "Invalid Price Item",
                "price": "-100.00",
                "is_available": "on",
            },
            follow=True,
        )
        self.assertFalse(MenuItem.objects.filter(name="Invalid Price Item").exists())

    # --- TABLE MANAGEMENT TESTS ---

    def test_table_crud(self):
        # Create Table
        response = self.client.post(
            reverse("manage_tables_save"),
            {"name": "VIP-Table-1", "capacity": 8, "status": "free"},
            follow=True,
        )
        tbl = DiningTable.objects.get(name="VIP-Table-1")
        self.assertEqual(tbl.capacity, 8)

        # Edit Table
        self.client.post(
            reverse("manage_tables_edit", kwargs={"table_id": tbl.pk}),
            {"name": "VIP-Table-1", "capacity": 10, "status": "reserved"},
            follow=True,
        )
        tbl.refresh_from_db()
        self.assertEqual(tbl.capacity, 10)
        self.assertEqual(tbl.status, "reserved")

        # Delete Table
        self.client.post(
            reverse("manage_tables_delete", kwargs={"table_id": tbl.pk}),
            follow=True,
        )
        self.assertFalse(DiningTable.objects.filter(pk=tbl.pk).exists())

    # --- SETTINGS TESTS ---

    def test_settings_update(self):
        response = self.client.post(
            reverse("settings"),
            {
                "restaurant_name": "Royal Spice Restaurant",
                "address": "123 Food Street, Lahore",
                "phone": "+92 300 1234567",
                "tax_rate": "16.00",
                "currency": "PKR",
            },
            follow=True,
        )
        self.assertRedirects(response, reverse("settings"))
        s = Setting.objects.first()
        self.assertEqual(s.restaurant_name, "Royal Spice Restaurant")
        self.assertEqual(s.tax_rate, Decimal("16.00"))

    # --- PERMISSIONS TEST ---

    def test_role_access_control(self):
        self.client.logout()
        # Login as Waiter
        self.client.login(username="waiter", password="demo123")

        for url_name in ["manage_categories", "manage_menu", "manage_tables", "settings"]:
            res = self.client.get(reverse(url_name))
            self.assertEqual(res.status_code, 403)
