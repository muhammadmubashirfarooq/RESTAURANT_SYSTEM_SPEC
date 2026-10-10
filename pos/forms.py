from django import forms
from .models import Category, MenuItem, DiningTable, Setting


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "sort_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Category Name (e.g. Starters)"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Category name cannot be empty.")
        return name


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ["category", "name", "description", "price", "image", "is_available"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Item Name"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Description"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "image": forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "is_available": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is not None and price < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return price


class DiningTableForm(forms.ModelForm):
    class Meta:
        model = DiningTable
        fields = ["name", "capacity", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Table Name (e.g. T-13)"}),
            "capacity": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_capacity(self):
        capacity = self.cleaned_data.get("capacity")
        if capacity is not None and capacity < 1:
            raise forms.ValidationError("Capacity must be at least 1.")
        return capacity


class SettingForm(forms.ModelForm):
    class Meta:
        model = Setting
        fields = ["restaurant_name", "address", "phone", "tax_rate", "currency"]
        widgets = {
            "restaurant_name": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "tax_rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "currency": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_tax_rate(self):
        tax_rate = self.cleaned_data.get("tax_rate")
        if tax_rate is not None and tax_rate < 0:
            raise forms.ValidationError("Tax rate cannot be negative.")
        return tax_rate
