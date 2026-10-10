-- Restaurant Management System: PostgreSQL schema
-- Run: psql -U postgres -d restaurant -f restaurant_schema.sql

-- ========== ENUM TYPES ==========
CREATE TYPE order_type      AS ENUM ('dine_in', 'takeaway', 'delivery');
CREATE TYPE order_status    AS ENUM ('pending', 'preparing', 'ready', 'served', 'completed', 'cancelled');
CREATE TYPE item_status     AS ENUM ('pending', 'preparing', 'ready', 'served', 'cancelled');
CREATE TYPE table_status    AS ENUM ('free', 'occupied', 'reserved');
CREATE TYPE payment_method  AS ENUM ('cash', 'card', 'online');
CREATE TYPE payment_status  AS ENUM ('unpaid', 'partial', 'paid', 'refunded');
CREATE TYPE reservation_status AS ENUM ('booked', 'seated', 'cancelled', 'no_show');
CREATE TYPE stock_move_type AS ENUM ('purchase', 'usage', 'waste', 'adjustment');
CREATE TYPE purchase_status AS ENUM ('draft', 'ordered', 'received', 'cancelled');

-- ========== USERS & ROLES ==========
CREATE TABLE roles (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(30) UNIQUE NOT NULL   -- admin, manager, cashier, waiter, kitchen
);

CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    role_id       INT NOT NULL REFERENCES roles(id),
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(120) UNIQUE,
    phone         VARCHAR(20),
    password_hash TEXT NOT NULL,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE staff_attendance (
    id         SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id),
    check_in   TIMESTAMP NOT NULL,
    check_out  TIMESTAMP
);

-- ========== MENU ==========
CREATE TABLE categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(80) NOT NULL,
    sort_order  INT DEFAULT 0,
    is_active   BOOLEAN DEFAULT TRUE
);

CREATE TABLE menu_items (
    id           SERIAL PRIMARY KEY,
    category_id  INT NOT NULL REFERENCES categories(id),
    name         VARCHAR(120) NOT NULL,
    description  TEXT,
    base_price   NUMERIC(10,2) NOT NULL CHECK (base_price >= 0),
    image_url    TEXT,
    is_available BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMP DEFAULT NOW()
);

-- Size / portion variants (Small, Medium, Large)
CREATE TABLE item_variants (
    id            SERIAL PRIMARY KEY,
    menu_item_id  INT NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    name          VARCHAR(50) NOT NULL,
    extra_price   NUMERIC(10,2) DEFAULT 0
);

-- Add-ons (extra cheese, extra sauce)
CREATE TABLE addons (
    id     SERIAL PRIMARY KEY,
    name   VARCHAR(80) NOT NULL,
    price  NUMERIC(10,2) NOT NULL DEFAULT 0
);

-- ========== TABLES & RESERVATIONS ==========
CREATE TABLE dining_tables (
    id        SERIAL PRIMARY KEY,
    name      VARCHAR(30) UNIQUE NOT NULL,   -- T1, T2, VIP-1
    capacity  INT NOT NULL CHECK (capacity > 0),
    status    table_status DEFAULT 'free'
);

CREATE TABLE customers (
    id             SERIAL PRIMARY KEY,
    full_name      VARCHAR(100) NOT NULL,
    phone          VARCHAR(20) UNIQUE,
    email          VARCHAR(120),
    address        TEXT,
    loyalty_points INT DEFAULT 0,
    created_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE reservations (
    id           SERIAL PRIMARY KEY,
    customer_id  INT REFERENCES customers(id),
    table_id     INT NOT NULL REFERENCES dining_tables(id),
    guests       INT NOT NULL,
    reserved_at  TIMESTAMP NOT NULL,
    status       reservation_status DEFAULT 'booked',
    notes        TEXT
);

-- ========== ORDERS ==========
CREATE TABLE orders (
    id              SERIAL PRIMARY KEY,
    order_no        VARCHAR(20) UNIQUE NOT NULL,
    order_type      order_type NOT NULL,
    table_id        INT REFERENCES dining_tables(id),     -- dine_in only
    customer_id     INT REFERENCES customers(id),
    waiter_id       INT REFERENCES users(id),
    status          order_status DEFAULT 'pending',
    payment_status  payment_status DEFAULT 'unpaid',
    subtotal        NUMERIC(10,2) DEFAULT 0,
    discount        NUMERIC(10,2) DEFAULT 0,
    tax             NUMERIC(10,2) DEFAULT 0,
    total           NUMERIC(10,2) DEFAULT 0,
    delivery_address TEXT,
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    closed_at       TIMESTAMP
);

CREATE TABLE order_items (
    id              SERIAL PRIMARY KEY,
    order_id        INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id    INT NOT NULL REFERENCES menu_items(id),
    variant_id      INT REFERENCES item_variants(id),
    quantity        INT NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(10,2) NOT NULL,     -- price at time of order
    status          item_status DEFAULT 'pending',
    special_note    TEXT
);

CREATE TABLE order_item_addons (
    order_item_id  INT NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
    addon_id       INT NOT NULL REFERENCES addons(id),
    price          NUMERIC(10,2) NOT NULL,
    PRIMARY KEY (order_item_id, addon_id)
);

CREATE TABLE payments (
    id          SERIAL PRIMARY KEY,
    order_id    INT NOT NULL REFERENCES orders(id),
    cashier_id  INT REFERENCES users(id),
    method      payment_method NOT NULL,
    amount      NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    reference   VARCHAR(100),                  -- card / transaction ref
    paid_at     TIMESTAMP DEFAULT NOW()
);

-- ========== INVENTORY ==========
CREATE TABLE suppliers (
    id       SERIAL PRIMARY KEY,
    name     VARCHAR(120) NOT NULL,
    phone    VARCHAR(20),
    address  TEXT
);

CREATE TABLE ingredients (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(100) UNIQUE NOT NULL,
    unit           VARCHAR(20) NOT NULL,          -- kg, litre, piece
    current_stock  NUMERIC(12,3) DEFAULT 0,
    reorder_level  NUMERIC(12,3) DEFAULT 0,       -- low-stock alert threshold
    cost_per_unit  NUMERIC(10,2) DEFAULT 0
);

-- Recipe: which ingredient and how much per menu item
CREATE TABLE recipes (
    menu_item_id   INT NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    ingredient_id  INT NOT NULL REFERENCES ingredients(id),
    quantity       NUMERIC(12,3) NOT NULL,
    PRIMARY KEY (menu_item_id, ingredient_id)
);

CREATE TABLE purchases (
    id           SERIAL PRIMARY KEY,
    supplier_id  INT NOT NULL REFERENCES suppliers(id),
    status       purchase_status DEFAULT 'draft',
    total_cost   NUMERIC(12,2) DEFAULT 0,
    created_at   TIMESTAMP DEFAULT NOW(),
    received_at  TIMESTAMP
);

CREATE TABLE purchase_items (
    id             SERIAL PRIMARY KEY,
    purchase_id    INT NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    ingredient_id  INT NOT NULL REFERENCES ingredients(id),
    quantity       NUMERIC(12,3) NOT NULL,
    unit_cost      NUMERIC(10,2) NOT NULL
);

CREATE TABLE stock_movements (
    id             SERIAL PRIMARY KEY,
    ingredient_id  INT NOT NULL REFERENCES ingredients(id),
    move_type      stock_move_type NOT NULL,
    quantity       NUMERIC(12,3) NOT NULL,       -- + in, - out
    order_id       INT REFERENCES orders(id),
    purchase_id    INT REFERENCES purchases(id),
    created_at     TIMESTAMP DEFAULT NOW()
);

-- ========== SETTINGS ==========
CREATE TABLE settings (
    key    VARCHAR(50) PRIMARY KEY,              -- tax_rate, restaurant_name, currency
    value  TEXT NOT NULL
);

-- ========== INDEXES (speed) ==========
CREATE INDEX idx_orders_status     ON orders(status);
CREATE INDEX idx_orders_created    ON orders(created_at);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_payments_order    ON payments(order_id);
CREATE INDEX idx_stock_ingredient  ON stock_movements(ingredient_id);

-- ========== SEED DATA ==========
INSERT INTO roles (name) VALUES ('admin'), ('manager'), ('cashier'), ('waiter'), ('kitchen');
INSERT INTO settings (key, value) VALUES
    ('restaurant_name', 'My Restaurant'),
    ('currency', 'PKR'),
    ('tax_rate', '0');
