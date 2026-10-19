# Deployment Guide: Restaurant POS & Management System

This guide outlines how to deploy the **Spice & Flavor Restaurant POS + Management System** to production platforms such as **Render** or **Railway** using PostgreSQL and Gunicorn.

---

## 1. Prerequisites

- A [GitHub](https://github.com/) repository containing the codebase.
- A free account on [Render](https://render.com/) or [Railway](https://railway.app/).
- A generated random `SECRET_KEY` for Django.

---

## 2. Deploying to Render (Recommended)

### Option A: Automated Blueprint Deployment (Fastest)
1. Push your repository to GitHub.
2. Log into your [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** -> **Blueprint**.
4. Connect your GitHub repository.
5. Render will detect `render.yaml` and automatically configure:
   - A **PostgreSQL Database** (`restaurant-pos-db`).
   - A **Web Service** (`restaurant-pos-system`) with Python runtime.
   - Build & Start commands, plus environment variable wiring.
6. Click **Apply**. Render will provision the database, install requirements, run migrations, seed demo users and menu, collect static files, and start Gunicorn.

---

### Option B: Manual Web Service + PostgreSQL Setup

#### Step 1: Provision a PostgreSQL Database
1. In Render, click **New +** -> **PostgreSQL**.
2. Give it a name (e.g., `restaurant-pos-db`).
3. Select the **Free** instance type.
4. Click **Create Database**.
5. Once created, copy the **Internal Database URL** (or External URL).

#### Step 2: Create Web Service
1. Click **New +** -> **Web Service**.
2. Connect your GitHub repository.
3. Configure the service settings:
   - **Environment:** `Python 3`
   - **Region:** Same region as your database (e.g. Oregon).
   - **Branch:** `main`
   - **Build Command:**
     ```bash
     pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate && python manage.py seed_demo
     ```
   - **Start Command:**
     ```bash
     gunicorn config.wsgi:application
     ```
   - **Instance Type:** `Free`

#### Step 3: Configure Environment Variables
In the **Environment** tab of your Render Web Service, add:

| Key | Value | Description |
|---|---|---|
| `SECRET_KEY` | *(Generate a 50+ char random string)* | Required in production |
| `DEBUG` | `False` | Disables debug mode in production |
| `ALLOWED_HOSTS` | `.onrender.com,localhost,127.0.0.1` | Allowed domain names |
| `DATABASE_URL` | *(Paste PostgreSQL URL from Step 1)* | Automatically enables PostgreSQL |
| `PYTHON_VERSION` | `3.11.9` | Recommended Python version |

4. Click **Deploy**.
5. When the deploy completes, open your `https://your-service.onrender.com` URL.
6. Log in with any demo credential (e.g., `admin / admin123` or `manager / demo123`).

---

## 3. Deploying to Railway

1. Log into [Railway.app](https://railway.app/).
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select your repository.
4. Click **+ New** -> **Database** -> **Add PostgreSQL**.
5. In the Web Service settings:
   - Add Environment Variables:
     - `SECRET_KEY`: *(random string)*
     - `DEBUG`: `False`
     - `ALLOWED_HOSTS`: `*.railway.app,localhost,127.0.0.1`
     - `DATABASE_URL`: `${{Postgres.DATABASE_URL}}`
   - Set Build Command:
     ```bash
     pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate && python manage.py seed_demo
     ```
   - Set Start Command:
     ```bash
     gunicorn config.wsgi:application
     ```
6. In **Settings**, generate a public Railway Domain.
7. Open the generated domain to verify the application.

---

## 4. Production Checklist

- [x] **DEBUG:** Set to `False` in production.
- [x] **SECRET_KEY:** Loaded strictly from environment variable, never committed to git.
- [x] **WhiteNoise:** Serves compressed static assets via `whitenoise.middleware.WhiteNoiseMiddleware`.
- [x] **Database:** Automatic fallback to SQLite locally; auto-connects to PostgreSQL in production via `DATABASE_URL`.
- [x] **Gunicorn:** Handles production HTTP requests concurrently.
- [x] **Error Pages:** Custom, user-friendly 404 and 500 error pages.
- [x] **Demo Data:** `python manage.py seed_demo` can be safely rerun anytime to refresh demo data without duplicate orders.
