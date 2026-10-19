# Spice & Flavor - Restaurant POS & Management System

> A modern, responsive **Restaurant Point of Sale (POS) & Operations Management System** built with **Python (Django 5)**, **HTMX**, **Bootstrap 5**, and **Chart.js**.

---

## 🍽️ Overview

**Spice & Flavor POS** streamlines restaurant operations from table ordering to kitchen preparation, payment processing, and executive sales analytics:

```
Waiter creates order on Table ➔ Kitchen receives order live (KDS) ➔ Kitchen marks ready 
➔ Waiter serves food ➔ Cashier bills, applies discounts & prints receipt ➔ Manager reviews dashboard & sales reports
```

Built with role-based workflows for **Admin**, **Manager**, **Waiter**, **Kitchen**, and **Cashier**, optimized for both desktop and tablet screens.

---

## ✨ Features

- **Role-Based Workflows & Security**:
  - Automatic home-screen routing upon login based on staff role.
  - Strict server-side permission checks with `@role_required` protecting every route.
- **Interactive Floor & Dining Tables (Waiter)**:
  - Visual status color codes: **Free (Green)**, **Occupied (Red)**, and **Reserved (Orange)**.
  - One-tap order creation on open tables; instant order review on occupied tables.
- **Fast Touch-Friendly Order Taking (Waiter)**:
  - Category tabs and instant live search.
  - Real-time HTMX cart with quantity controls, unit price locking, special cooking instructions, and subtotal calculation.
- **Live Kitchen Display System / KDS (Kitchen)**:
  - 3-column kanban board: **Pending**, **Preparing**, and **Ready**.
  - 5-second automatic HTMX polling for live ticket updates without page reloads.
  - Elapsed timers and glowing pulse indicator for new orders.
  - One-click item preparation toggles and batch order transitions.
- **Cashier Billing & Payments (Cashier)**:
  - Active open bills list with order totals and remaining balance.
  - Server-validated discounts (percentage or flat PKR) and automatic tax calculation from store settings.
  - Split payments support across **Cash**, **Card**, and **Online**.
  - Change due calculation. Automatic order completion and instant table release upon full payment.
  - Pure-Python branded PDF receipt download powered by `xhtml2pdf`.
- **Menu & Floor Management (Manager)**:
  - Full CRUD for menu items and categories with image uploads.
  - Instant one-click menu item availability toggle.
  - Dining table capacity and layout management.
  - Store settings (Restaurant name, address, contact, tax rate %, currency symbol).
- **Executive Analytics Dashboard (Admin / Manager)**:
  - Real-time KPI cards: Today's Net Sales, Orders Count, Average Order Value (AOV), and Active Operations.
  - Chart.js interactive 7-day sales line chart with gradient fill and tooltips.
  - Chart.js doughnut chart breaking down orders by status.
  - Ranked Top 5 Best-Selling Menu Items with quantity sold and revenue share.
- **Comprehensive Reports & Data Export (Admin / Manager)**:
  - Flexible date-range filter with quick presets (*Today*, *Last 7 Days*, *Last 14 Days*, *This Month*, *Last 30 Days*).
  - Daily sales breakdown (Orders count, Subtotal, Discount, Tax, Net Sales, AOV).
  - Itemized sales ledger with quantity and revenue.
  - Payment method distribution (*Cash*, *Card*, *Online*) with reconciliation down to the cent.
  - One-click CSV export at `/reports/export.csv`.
- **Production Polish**:
  - Friendly, branded custom **404 Page Not Found** and **500 Server Error** pages.
  - High-contrast typography and touch targets optimized for tablet screens.
  - Idempotent `seed_demo` command safe to run repeatedly.

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| **Backend Framework** | Python 3.11+ / Django 5 |
| **Frontend UI** | Django Templates, HTML5, Vanilla CSS3 (Custom Dark Theme) |
| **Interactive Components** | [HTMX](https://htmx.org/) (Dynamic live updates & cart manipulation) |
| **Styling & Grid** | [Bootstrap 5](https://getbootstrap.com/) & [FontAwesome 6](https://fontawesome.com/) |
| **Data Visualization** | [Chart.js 4](https://www.chartjs.org/) |
| **PDF Generation** | [xhtml2pdf](https://xhtml2pdf.readthedocs.io/) |
| **Static Files** | [WhiteNoise](http://whitenoise.evans.io/) |
| **Database** | SQLite (Local Dev) / PostgreSQL (Production via `dj-database-url`) |
| **WSGI Server** | Gunicorn (Production) |

---

## 🔑 Demo Credentials

All test accounts are pre-configured with quick auto-fill buttons on the login screen:

| Username | Password | Role | Default Landing Page |
|---|---|---|---|
| **admin** | `admin123` | **Admin** | Dashboard (`/dashboard/`) |
| **manager** | `demo123` | **Manager** | Dashboard (`/dashboard/`) |
| **waiter** | `demo123` | **Waiter** | Tables Grid (`/tables/`) |
| **kitchen** | `demo123` | **Kitchen** | Kitchen Board (`/kitchen/`) |
| **cashier** | `demo123` | **Cashier** | Billing List (`/billing/`) |

---

## 🚀 Setup Steps for Windows

### 1. Clone the Repository
```powershell
git clone https://github.com/your-username/restaurant_management_system.git
cd restaurant_management_system
```

### 2. Create and Activate Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
*(Optionally adjust `SECRET_KEY`, `DEBUG`, or `ALLOWED_HOSTS` inside `.env`)*

### 5. Run Database Migrations
```powershell
python manage.py migrate
```

### 6. Seed Demo Data
Populates roles, demo users, tables, categories, 30+ Pakistani cuisine menu items, and historical orders across the last 14 days:
```powershell
python manage.py seed_demo
```
*(Note: Safe to run repeatedly anytime to refresh demo data)*

### 7. Run Development Server
```powershell
python manage.py runserver
```
Open **`http://127.0.0.1:8000/`** in your browser.

---

## 🧪 Running Tests

The test suite covers order calculations, role permissions, payment workflows, status transitions, report generation, and error handling:

```powershell
# Run all test suites
python manage.py test

# Run individual phase tests
python manage.py test pos.tests.test_phase1
python manage.py test pos.tests.test_phase6
python manage.py test pos.tests.test_phase7
```

---

## 📸 Screenshots

*(Place application preview screenshots in this section)*

### 1. Sales & Operations Dashboard
```
[ Screenshot Placeholder: Dashboard KPI Cards, 7-Day Chart, and Top 5 Items ]
```

### 2. Dining Tables Floor Plan
```
[ Screenshot Placeholder: Free, Occupied, and Reserved Table Cards ]
```

### 3. Touch-Friendly Live Order Screen
```
[ Screenshot Placeholder: Category Tabs, Search Bar, and Live HTMX Cart ]
```

### 4. Kitchen Display Board (KDS)
```
[ Screenshot Placeholder: Kanban Columns: Pending, Preparing, Ready with Timers ]
```

### 5. Cashier Billing & PDF Receipt
```
[ Screenshot Placeholder: Bill Settlement Modal and PDF Receipt ]
```

### 6. Detailed Sales Reports & Analytics
```
[ Screenshot Placeholder: Date Filter, Daily Sales Table, Item Breakdown, and Payment Methods ]
```

---

## 🌐 Production Deployment

Refer to [DEPLOY.md](DEPLOY.md) for full deployment instructions on **Render** and **Railway** with PostgreSQL, Gunicorn, and WhiteNoise.
