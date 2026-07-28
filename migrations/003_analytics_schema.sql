-- Replaces the three toy tables with a star schema built for practising
-- advanced SQL and, later, advanced Power BI modelling.
--
-- What each piece is here to exercise:
--
--   recursive CTEs      employees.manager_id, categories.parent_category_id
--                       are self-referencing hierarchies
--   window functions    orders / order_items span six years, so running
--                       totals, LAG/LEAD, RANK and moving averages all work
--   temporal joins      product_price_history is a slowly-changing dimension
--                       (type 2): join on a date BETWEEN valid_from/valid_to
--   many-to-many        order_items, campaign_customers
--   multiple fact grains order_items (line), returns (line), payments (order),
--                       inventory_snapshots (product-month) — the interesting
--                       case for both SQL and DAX, because you cannot simply
--                       join them together
--   time intelligence   dim_date supports YoY / YTD / fiscal periods without
--                       date arithmetic in every query
--   geography           cities carry latitude/longitude for Power BI maps
--
-- Power BI note: dim_date, cities/countries/regions, categories and employees
-- are conformed dimensions shared by several facts — a proper star, not a
-- flat table. That is what makes relationships, drill-down hierarchies and
-- cross-filtering worth practising.

DROP TABLE IF EXISTS inventory_snapshots CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS returns CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS campaign_customers CASCADE;
DROP TABLE IF EXISTS campaigns CASCADE;
DROP TABLE IF EXISTS product_price_history CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS categories CASCADE;
DROP TABLE IF EXISTS suppliers CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS cities CASCADE;
DROP TABLE IF EXISTS countries CASCADE;
DROP TABLE IF EXISTS regions CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;

-- ---------------------------------------------------------------- dimensions

CREATE TABLE dim_date (
    date_key        DATE PRIMARY KEY,
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      TEXT    NOT NULL,
    day_of_month    INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,   -- 1 = Monday
    day_name        TEXT    NOT NULL,
    week_of_year    INTEGER NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    fiscal_year     INTEGER NOT NULL,   -- fiscal year starts in April
    fiscal_quarter  INTEGER NOT NULL
);

CREATE TABLE regions (
    region_id   INTEGER PRIMARY KEY,
    region_name TEXT NOT NULL
);

CREATE TABLE countries (
    country_id   INTEGER PRIMARY KEY,
    country_name TEXT NOT NULL,
    iso_code     TEXT NOT NULL,
    region_id    INTEGER NOT NULL REFERENCES regions(region_id)
);

CREATE TABLE cities (
    city_id    INTEGER PRIMARY KEY,
    city_name  TEXT NOT NULL,
    country_id INTEGER NOT NULL REFERENCES countries(country_id),
    latitude   NUMERIC(9, 6),
    longitude  NUMERIC(9, 6)
);

-- Self-referencing: manager_id points at another employee. Recursive CTE
-- territory (org chart depth, reporting lines, rollups by manager).
CREATE TABLE employees (
    employee_id     INTEGER PRIMARY KEY,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    title           TEXT NOT NULL,
    manager_id      INTEGER REFERENCES employees(employee_id),
    hire_date       DATE NOT NULL,
    termination_date DATE,
    city_id         INTEGER REFERENCES cities(city_id),
    base_salary     NUMERIC(10, 2) NOT NULL,
    commission_rate NUMERIC(4, 3) NOT NULL DEFAULT 0
);

-- Also self-referencing, three levels deep.
CREATE TABLE categories (
    category_id        INTEGER PRIMARY KEY,
    category_name      TEXT NOT NULL,
    parent_category_id INTEGER REFERENCES categories(category_id),
    category_level     INTEGER NOT NULL
);

CREATE TABLE suppliers (
    supplier_id       INTEGER PRIMARY KEY,
    supplier_name     TEXT NOT NULL,
    city_id           INTEGER REFERENCES cities(city_id),
    lead_time_days    INTEGER NOT NULL,
    reliability_score NUMERIC(4, 2) NOT NULL
);

CREATE TABLE products (
    product_id      INTEGER PRIMARY KEY,
    product_name    TEXT NOT NULL,
    category_id     INTEGER NOT NULL REFERENCES categories(category_id),
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    unit_cost       NUMERIC(10, 2) NOT NULL,
    list_price      NUMERIC(10, 2) NOT NULL,
    weight_kg       NUMERIC(7, 3),
    launch_date     DATE NOT NULL,
    is_discontinued BOOLEAN NOT NULL DEFAULT FALSE
);

-- Slowly-changing dimension, type 2. To price an order line correctly you must
-- join on the order date falling between valid_from and valid_to.
CREATE TABLE product_price_history (
    price_history_id INTEGER PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(product_id),
    unit_price       NUMERIC(10, 2) NOT NULL,
    valid_from       DATE NOT NULL,
    valid_to         DATE,               -- NULL = still current
    is_current       BOOLEAN NOT NULL
);

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email         TEXT NOT NULL,
    city_id       INTEGER NOT NULL REFERENCES cities(city_id),
    segment       TEXT NOT NULL,         -- Consumer / Corporate / Home Office
    signup_date   DATE NOT NULL,
    credit_limit  NUMERIC(10, 2) NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE campaigns (
    campaign_id   INTEGER PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    channel       TEXT NOT NULL,
    start_date    DATE NOT NULL,
    end_date      DATE NOT NULL,
    budget        NUMERIC(12, 2) NOT NULL
);

-- Many-to-many bridge.
CREATE TABLE campaign_customers (
    campaign_id     INTEGER NOT NULL REFERENCES campaigns(campaign_id),
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    contacted_date  DATE NOT NULL,
    responded       BOOLEAN NOT NULL,
    PRIMARY KEY (campaign_id, customer_id)
);

-- --------------------------------------------------------------------- facts

CREATE TABLE orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    employee_id   INTEGER REFERENCES employees(employee_id),
    order_date    DATE NOT NULL REFERENCES dim_date(date_key),
    required_date DATE,
    shipped_date  DATE,
    status        TEXT NOT NULL,        -- Completed / Shipped / Pending / Cancelled
    order_channel TEXT NOT NULL,        -- Web / Phone / Partner / Retail
    ship_city_id  INTEGER REFERENCES cities(city_id),
    freight       NUMERIC(10, 2) NOT NULL DEFAULT 0
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    NUMERIC(10, 2) NOT NULL,
    discount_pct  NUMERIC(4, 3) NOT NULL DEFAULT 0,
    line_total    NUMERIC(12, 2) NOT NULL
);

CREATE TABLE returns (
    return_id        INTEGER PRIMARY KEY,
    order_item_id    INTEGER NOT NULL REFERENCES order_items(order_item_id),
    return_date      DATE NOT NULL,
    quantity_returned INTEGER NOT NULL,
    reason           TEXT NOT NULL,
    refund_amount    NUMERIC(12, 2) NOT NULL
);

CREATE TABLE payments (
    payment_id   INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders(order_id),
    payment_date DATE NOT NULL,
    amount       NUMERIC(12, 2) NOT NULL,
    method       TEXT NOT NULL
);

-- Periodic snapshot fact: one row per product per month.
CREATE TABLE inventory_snapshots (
    snapshot_id    INTEGER PRIMARY KEY,
    product_id     INTEGER NOT NULL REFERENCES products(product_id),
    snapshot_date  DATE NOT NULL,
    units_on_hand  INTEGER NOT NULL,
    units_on_order INTEGER NOT NULL,
    reorder_level  INTEGER NOT NULL
);

-- ------------------------------------------------------------------- indexes
-- Foreign keys are not indexed automatically in Postgres; these are the joins
-- and filters the practice queries will actually hit.

CREATE INDEX idx_orders_customer     ON orders(customer_id);
CREATE INDEX idx_orders_employee     ON orders(employee_id);
CREATE INDEX idx_orders_date         ON orders(order_date);
CREATE INDEX idx_order_items_order   ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_returns_item        ON returns(order_item_id);
CREATE INDEX idx_payments_order      ON payments(order_id);
CREATE INDEX idx_inventory_product   ON inventory_snapshots(product_id, snapshot_date);
CREATE INDEX idx_products_category   ON products(category_id);
CREATE INDEX idx_customers_city      ON customers(city_id);
CREATE INDEX idx_employees_manager   ON employees(manager_id);
CREATE INDEX idx_price_history       ON product_price_history(product_id, valid_from);

-- The read-only role needs SELECT on everything created above. Default
-- privileges from 002 cover tables created later, but granting explicitly
-- means this migration is correct on its own.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sql_assistant_ro;
