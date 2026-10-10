import random
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.db import transaction

from pos.models import Category, MenuItem, DiningTable, Order, OrderItem, Payment, Setting


class Command(BaseCommand):
    help = "Seed database with demo roles, users, categories, menu items, tables, and past orders."

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("Starting demo seeding..."))

        # 1. Setting
        setting, _ = Setting.objects.get_or_create(id=1)
        setting.restaurant_name = "Spice & Flavor Bistro"
        setting.address = "Plot 45, Block 6, PECHS, Karachi, Pakistan"
        setting.phone = "+92 21 34567890"
        setting.tax_rate = Decimal("13.00")
        setting.currency = "PKR"
        setting.save()
        self.stdout.write(self.style.SUCCESS("[OK] Default setting created."))

        # 2. Roles / Groups
        roles = ["Admin", "Manager", "Waiter", "Kitchen", "Cashier"]
        group_objs = {}
        for role_name in roles:
            g, _ = Group.objects.get_or_create(name=role_name)
            group_objs[role_name] = g
        self.stdout.write(self.style.SUCCESS("[OK] Groups created: Admin, Manager, Waiter, Kitchen, Cashier."))

        # 3. Users
        users_data = [
            ("admin", "admin123", "Admin", True),
            ("manager", "demo123", "Manager", False),
            ("waiter", "demo123", "Waiter", False),
            ("kitchen", "demo123", "Kitchen", False),
            ("cashier", "demo123", "Cashier", False),
        ]

        created_users = {}
        for username, password, role_name, is_super in users_data:
            user = User.objects.filter(username=username).first()
            if not user:
                if is_super:
                    user = User.objects.create_superuser(username=username, email="", password=password)
                else:
                    user = User.objects.create_user(username=username, email="", password=password)
            user.set_password(password)
            user.save()
            user.groups.add(group_objs[role_name])
            created_users[role_name] = user
            self.stdout.write(self.style.SUCCESS(f"  - Created user: {username} ({role_name})"))

        # 4. Tables (12 tables)
        tables_data = [
            ("T1", 2), ("T2", 2), ("T3", 4), ("T4", 4),
            ("T5", 4), ("T6", 6), ("T7", 6), ("T8", 8),
            ("VIP-1", 4), ("VIP-2", 6), ("Outdoor-1", 4), ("Outdoor-2", 4),
        ]
        created_tables = []
        for name, cap in tables_data:
            t, _ = DiningTable.objects.get_or_create(name=name, defaults={"capacity": cap, "status": DiningTable.Status.FREE})
            created_tables.append(t)
        self.stdout.write(self.style.SUCCESS(f"[OK] Created {len(created_tables)} dining tables."))

        # 5. Categories (6 categories)
        categories_data = [
            ("Starters & Appetizers", 1),
            ("Traditional Karahi & Handi", 2),
            ("BBQ & Grills", 3),
            ("Naan & Breads", 4),
            ("Desserts & Sweets", 5),
            ("Beverages & Drinks", 6),
        ]
        created_categories = []
        for cat_name, order in categories_data:
            c, _ = Category.objects.get_or_create(name=cat_name, defaults={"sort_order": order})
            created_categories.append(c)
        self.stdout.write(self.style.SUCCESS(f"[OK] Created {len(created_categories)} categories."))

        # 6. Menu Items (~30 items)
        items_by_cat = {
            "Starters & Appetizers": [
                ("Chicken Reshmi Roll", "Juicy reshmi kabab wrapped in crispy paratha", Decimal("350.00")),
                ("Finger Fish with Tartar Sauce", "Crispy golden fried fish fillets", Decimal("850.00")),
                ("Chicken Wings (8 pcs)", "Spicy glazed fried chicken wings", Decimal("650.00")),
                ("Soup of the Day (Hot & Sour)", "Rich spicy Chinese soup", Decimal("420.00")),
                ("French Fries Large", "Crispy salted potato fries", Decimal("300.00")),
            ],
            "Traditional Karahi & Handi": [
                ("Chicken Karahi Full", "Classic Pakhtun style fresh tomato gravy chicken", Decimal("1850.00")),
                ("Chicken Karahi Half", "Half portion fresh tomato gravy chicken", Decimal("1050.00")),
                ("Mutton White Handi Full", "Creamy mild boneless mutton handi", Decimal("2600.00")),
                ("Chicken Boneless Handi", "Rich butter gravy boneless chicken handi", Decimal("1450.00")),
                ("Paneer Reshmi Handi", "Cottage cheese cubes in velvety mild gravy", Decimal("1100.00")),
            ],
            "BBQ & Grills": [
                ("Chicken Tikka Chest", "Charcoal grilled marinated chicken quarter", Decimal("480.00")),
                ("Chicken Seekh Kabab (4 pcs)", "Spiced minced chicken skewers", Decimal("620.00")),
                ("Beef Behari Kabab", "Melt in mouth tender marinated beef strips", Decimal("890.00")),
                ("Chicken Malai Boti (10 pcs)", "Creamy cardamom flavored chicken skewers", Decimal("950.00")),
                ("Fish Tikka BBQ", "Spiced grilled fish cubes", Decimal("1150.00")),
            ],
            "Naan & Breads": [
                ("Roghni Naan", "Sesame topped buttered fluffy naan", Decimal("90.00")),
                ("Garlic Naan", "Fresh garlic and coriander butter naan", Decimal("110.00")),
                ("Cheese Naan", "Stuffed mozzarella and cheddar naan", Decimal("380.00")),
                ("Kandhari Naan", "Traditional Afghan style large crisp naan", Decimal("100.00")),
                ("Plain Tandoori Roti", "Whole wheat tandoor roti", Decimal("40.00")),
            ],
            "Desserts & Sweets": [
                ("Shahi Kheer Cup", "Traditional saffron rice pudding", Decimal("220.00")),
                ("Hot Gulab Jamun (2 pcs)", "Warm syrup soaked milk dumplings", Decimal("250.00")),
                ("Molten Lava Cake", "Served warm with vanilla ice cream scoop", Decimal("650.00")),
                ("Zafrani Matka Kulfi", "Authentic clay pot saffron kulfi", Decimal("280.00")),
            ],
            "Beverages & Drinks": [
                ("Fresh Mint Lemonade", "Crushed mint, lemon juice & soda", Decimal("250.00")),
                ("Sweet Lassi", "Traditional chilled yogurt drink", Decimal("220.00")),
                ("Pakola Ice Cream Soda Can", "Classic Pakistani soft drink", Decimal("120.00")),
                ("Soft Drink 1.5L", "Chilled Coke / Sprite / Fanta", Decimal("220.00")),
                ("Kashmiri Chai", "Pink tea with crushed pistachios & almonds", Decimal("180.00")),
                ("Mineral Water 1.5L", "Purified drinking water", Decimal("110.00")),
            ],
        }

        all_menu_items = []
        for cat in created_categories:
            for item_name, desc, price in items_by_cat.get(cat.name, []):
                mi, _ = MenuItem.objects.get_or_create(
                    category=cat,
                    name=item_name,
                    defaults={"description": desc, "price": price, "is_available": True}
                )
                all_menu_items.append(mi)
        self.stdout.write(self.style.SUCCESS(f"[OK] Created {len(all_menu_items)} menu items."))

        # 7. Past Orders (~40 orders spread over last 14 days)
        now = timezone.now()
        waiter = created_users["Waiter"]
        cashier = created_users["Cashier"]

        order_count = 0
        for i in range(40):
            days_ago = random.randint(0, 13)
            hours_ago = random.randint(1, 10)
            created_time = now - timedelta(days=days_ago, hours=hours_ago)
            table = random.choice(created_tables)

            order = Order.objects.create(
                order_type=Order.Type.DINE_IN,
                table=table,
                waiter=waiter,
                status=Order.Status.COMPLETED,
                discount=Decimal("0.00") if random.random() > 0.3 else Decimal("100.00"),
                tax_rate=setting.tax_rate,
                notes="Demo historical order",
                closed_at=created_time + timedelta(minutes=random.randint(25, 60))
            )
            order.created_at = created_time
            order.save()

            # Add 2-4 items per order
            selected_items = random.sample(all_menu_items, random.randint(2, 4))
            for mi in selected_items:
                qty = random.randint(1, 3)
                OrderItem.objects.create(
                    order=order,
                    menu_item=mi,
                    quantity=qty,
                    unit_price=mi.price,
                    status=OrderItem.Status.SERVED
                )

            # Payment
            pm_method = random.choice([Payment.Method.CASH, Payment.Method.CARD, Payment.Method.ONLINE])
            Payment.objects.create(
                order=order,
                cashier=cashier,
                method=pm_method,
                amount=order.total,
                reference=f"REF-{10000 + order.pk}"
            )
            order_count += 1

        self.stdout.write(self.style.SUCCESS(f"[OK] Created {order_count} past orders over the last 14 days."))
        self.stdout.write(self.style.SUCCESS("[OK] Seeding complete! Demo system is ready."))
