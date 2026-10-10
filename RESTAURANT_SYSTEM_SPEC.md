# Restaurant Management System: Complete Project Spec

> Give this whole file to Antigravity (or any AI coding agent) as the project brief.
> Build **phase by phase** (section 10). Do not skip ahead. Run and test after each phase.

---

## 1. What we are building

A **Restaurant POS + Management System** for a single restaurant, built in **Python (Django)**.
Staff use it on a PC/tablet browser inside the restaurant (local network) or via a hosted URL.

**Goal:** a polished, working **demo** for freelance clients. Priority is a smooth end-to-end flow
and a clean UI, not enterprise depth.

**Core flow in one line:**
Waiter takes order on a table -> Kitchen sees it live -> Kitchen marks ready -> Waiter serves -> Cashier bills and takes payment -> Manager sees sales dashboard.

---

## 2. Tech stack (fixed, do not change)

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Framework | Django 5 |
| Database | SQLite for dev, PostgreSQL for production |
| Frontend | Django templates + HTMX + Bootstrap 5 (CDN), Chart.js for charts |
| Auth | Django auth + Groups for roles |
| PDF receipt | WeasyPrint (or xhtml2pdf if WeasyPrint is hard to install on Windows) |
| Static files | WhiteNoise |
| Config | environment variables via `python-decouple` |

No React, no separate API server. Keep it a single Django project with one app named `pos`.

---

## 3. Roles and permissions

| Role (Django Group) | Can do |
|---|---|
| **Admin** | Everything, including user management and settings |
| **Manager** | Menu, tables, orders, payments, reports; cannot manage superusers |
| **Waiter** | Create/edit own open orders, view tables, mark items served |
| **Kitchen** | View kitchen screen, change item status (preparing / ready) |
| **Cashier** | View orders ready for billing, apply discount, take payment, print receipt |

After login, redirect each role to its home screen:
Admin/Manager -> Dashboard, Waiter -> Tables, Kitchen -> Kitchen screen, Cashier -> Billing list.

---

## 4. Screens

1. **Login** (clean, restaurant logo, role-based redirect)
2. **Dashboard** (Admin/Manager): today's sales, orders count, average order value, top 5 items, last 7 days sales line chart, orders by status
3. **Tables** (Waiter): grid of table cards coloured by status (free = green, occupied = red, reserved = orange). Click a free table to start an order; click an occupied table to open its order.
4. **Order screen** (Waiter): left side menu with category tabs and search; right side live cart with quantity +/-, item notes, subtotal. Buttons: *Send to kitchen*, *Cancel order*.
5. **Kitchen screen**: board with 3 columns (Pending / Preparing / Ready). Cards show table, items, notes, and elapsed time. Auto-refresh every 5 seconds via HTMX. One-click status buttons. New orders highlighted.
6. **Billing list** (Cashier): open orders with totals.
7. **Bill/Payment screen**: item list, discount input, tax, total, payment method (cash/card/online), amount received, change due. Buttons: *Take payment*, *Download receipt PDF*.
8. **Menu management** (Manager): categories and items CRUD, image upload, availability toggle.
9. **Table management** (Manager): add/edit tables, capacity.
10. **Reports** (Manager): date-range filter, sales by day, sales by item, sales by payment method, CSV export.
11. **Users** (Admin): create users and assign role.
12. **Settings** (Admin): restaurant name, address, phone, tax rate, currency symbol.

---

## 5. Order lifecycle

```
Order: pending -> preparing -> ready -> served -> completed (after full payment)
                                   \-> cancelled (any time before payment)

OrderItem: pending -> preparing -> ready -> served  (or cancelled)
```

Rules:
- Creating an order on a table sets the table to **occupied**.
- Completing payment (paid >= total) sets order to **completed**, sets `closed_at`, and frees the table.
- Order status is derived from its items: all ready = order ready; all served = order served.
- `unit_price` is copied from the menu at order time and never changes afterwards.
- Total = subtotal - discount + tax. Tax rate comes from Settings.
- A cancelled order frees the table.
- Unavailable menu items cannot be added to an order.

---

## 6. Data models

Use the models in **`restaurant_models.py`** (already provided): `Category`, `MenuItem`,
`DiningTable`, `Order`, `OrderItem`, `Payment`. Add one more:

```python
class Setting(models.Model):      # single-row settings
    restaurant_name = models.CharField(max_length=120, default="My Restaurant")
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="PKR")
```

Register all models in `admin.py` with sensible `list_display`, filters and search.

---

## 7. URL map

```
/                         -> role-based redirect
/login/  /logout/
/dashboard/
/tables/
/orders/new/<table_id>/
/orders/<id>/                 (order screen)
/orders/<id>/add-item/        (HTMX POST)
/orders/<id>/remove-item/<item_id>/
/orders/<id>/send/            (send to kitchen)
/orders/<id>/cancel/
/kitchen/                     (board)
/kitchen/partial/             (HTMX refresh fragment)
/kitchen/item/<id>/status/    (HTMX POST)
/billing/
/billing/<order_id>/          (bill + pay)
/billing/<order_id>/receipt.pdf
/manage/menu/  /manage/categories/  /manage/tables/
/reports/  /reports/export.csv
/users/  /settings/
```

---

## 8. Folder structure

```
restaurant/
|-- manage.py
|-- requirements.txt
|-- .env.example
|-- config/                 (settings, urls, wsgi)
|-- pos/
|   |-- models.py
|   |-- admin.py
|   |-- forms.py
|   |-- permissions.py      (role decorators/mixins)
|   |-- views/              (auth.py, tables.py, orders.py, kitchen.py, billing.py, manage.py, reports.py)
|   |-- urls.py
|   |-- services.py         (order totals, status transitions, payment logic)
|   |-- templates/pos/      (base.html, partials/, one folder per area)
|   |-- static/pos/         (css, js, img)
|   |-- management/commands/seed_demo.py
|   `-- tests/
`-- media/                  (uploaded images)
```

Keep business logic in `services.py`, views stay thin.

---

## 9. Quality requirements

- **UI:** modern, clean, big touch-friendly buttons (tablet use), consistent colours, orange accent. Responsive down to tablet width.
- **Security:** CSRF on all forms, role checks on every view, passwords hashed, `DEBUG=False` and `ALLOWED_HOSTS` from env in production.
- **Validation:** no negative quantities/prices, cannot pay more than needed without showing change, cannot close an order with unserved/unsent items without a warning.
- **Seed command:** `python manage.py seed_demo` creates groups, demo users, 6 categories, about 30 menu items (with prices in PKR), 12 tables, and about 40 past orders spread over the last 14 days so the dashboard looks alive.
- **Demo logins** (create in seed): `admin / admin123`, `manager / demo123`, `waiter / demo123`, `kitchen / demo123`, `cashier / demo123`.
- **Tests:** at least tests for order total calculation, status transitions, payment completing an order, and role permissions.
- **README:** setup steps, demo credentials, screenshots section, feature list.

---

## 10. Build phases (do one at a time, run after each)

**Phase 1: Foundation.** Project setup, `pos` app, models + migrations, admin registration, groups and role permissions, base template with navbar by role, login/logout with role redirect, `seed_demo` command (users, menu, tables).
*Done when:* every demo user can log in and lands on the right page; admin panel shows all data.

**Phase 2: Management screens.** Menu items, categories and tables CRUD pages (Manager), settings page.
*Done when:* manager can add a menu item with image and toggle availability.

**Phase 3: Order taking.** Tables grid, order screen with HTMX cart, send to kitchen.
*Done when:* waiter opens a free table, adds items, sends order, table turns red.

**Phase 4: Kitchen.** Kitchen board with auto-refresh and status buttons.
*Done when:* an order sent by a waiter appears on the kitchen screen within 5 seconds and status changes reflect back on the waiter's order.

**Phase 5: Billing.** Billing list, bill screen, discount, tax, payments (split payments allowed), change calculation, order completion, table freed, PDF receipt.
*Done when:* a full order can be paid and a receipt PDF downloaded.

**Phase 6: Dashboard and reports.** KPI cards, Chart.js charts, date-range reports, CSV export.
*Done when:* dashboard shows numbers matching the seeded orders.

**Phase 7: Polish and deploy.** UI cleanup, empty states, error pages (404/500), tests, README with screenshots, production settings, deploy to Render/Railway with PostgreSQL, load demo data.
*Done when:* a public URL works with the demo logins.

---

## 11. How the final product is delivered (the "outcome")

1. **Live demo link:** the hosted Django app (for example `https://your-restaurant-demo.onrender.com`) with demo credentials. This is what you send to clients.
2. **Source code:** GitHub repo with README, screenshots and feature list.
3. **Demo video:** 2-3 minute screen recording of the full flow (waiter -> kitchen -> cashier -> dashboard).
4. **Optional desktop packaging:** if a client wants a Windows `.exe`, wrap the same app with `pywebview` and build with `PyInstaller`, using SQLite so it runs fully offline on one PC.

---

## 12. Instructions for the coding agent

- Follow phases in order. At the end of each phase, run the server, run tests, and tell me exactly what to click to verify it.
- Before writing code in a phase, show a short plan (files you will create/change).
- Do not add features outside this spec. If something is unclear, make the simplest reasonable choice and note it.
- Keep code readable with short comments; no unused code.
- Never hardcode secrets; use `.env`.

---

## 13. Full-fledged extension (Phases 8 to 12)

Start these ONLY after Phases 1-7 are complete, tested and deployed. Reuse the table design from
`restaurant_schema.sql` (ingredients, recipes, suppliers, purchases, stock_movements, customers,
reservations, staff_attendance).

**Phase 8: Inventory and recipes.**
Ingredients CRUD (unit, current stock, reorder level, cost per unit). Recipe builder per menu item
(which ingredient, how much). When an order is **completed**, auto-deduct ingredient stock and log a
`StockMovement` (type: usage). Manual stock adjustment and waste entry. Low-stock alert badge on the
dashboard and a low-stock report. Optionally auto-mark a menu item unavailable when a key ingredient is out.
*Done when:* completing an order reduces stock correctly and low-stock items show on the dashboard.

**Phase 9: Suppliers and purchases.**
Suppliers CRUD, purchase orders (draft -> ordered -> received). Receiving a purchase increases stock
and logs a `StockMovement` (type: purchase). Cost per unit updates from the latest purchase.
Reports: purchases by supplier, stock valuation, profit estimate (sales minus ingredient cost).
*Done when:* a received purchase raises stock and appears in the profit report.

**Phase 10: Customers, loyalty and reservations.**
Customer records (name, phone, address). Attach customer to an order. Loyalty points (for example
1 point per 100 PKR, redeem as discount). Reservations calendar: book a table for date/time and guests,
status (booked / seated / cancelled / no-show); a reserved table shows orange on the Tables screen and
a "Seat now" button converts the reservation into an order.
*Done when:* a reservation can be booked, seated, and its customer earns loyalty points on payment.

**Phase 11: Takeaway, delivery and staff.**
Takeaway and delivery order types (no table; delivery needs address, phone and delivery fee; status
adds "out for delivery"). Staff attendance (check-in / check-out), shifts, and a simple monthly
attendance report. Waiter performance report (orders and sales per waiter).
*Done when:* a delivery order can be created, tracked to completion, and appears in reports by order type.

**Phase 12: Production polish.**
KOT (kitchen order ticket) and receipt print layouts for 80mm thermal printers, audit log of
sensitive actions (discounts, cancellations, price changes), daily closing report (cash drawer summary),
database backup command, rate limiting on login, and a Settings page for all configurable values.
*Done when:* the daily closing report matches the sum of payments for that day.

Same rules as before: one phase at a time, show a plan first, run tests, and tell me how to verify.
