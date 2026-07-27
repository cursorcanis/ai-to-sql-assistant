-- AI SQL Assistant — initial Postgres schema and sample data.
--
-- Run this once in the Supabase SQL Editor (Dashboard → SQL Editor → New query).
-- Safe to re-run: it drops and recreates the three tables.
--
-- Note on naming: the original SQLite schema used mixed case (CustomerID,
-- ProductName). Postgres folds unquoted identifiers to lowercase, so those
-- would have to be double-quoted in every generated query -- a reliability
-- problem when an LLM is writing the SQL. Everything is snake_case here so
-- queries work unquoted.

DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    city        TEXT,
    email       TEXT
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category     TEXT,
    price        NUMERIC(10, 2)
);

CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    product_id  INTEGER REFERENCES products(product_id),
    order_date  DATE,
    quantity    INTEGER,
    total       NUMERIC(10, 2)
);

INSERT INTO customers (customer_id, name, city, email) VALUES
    (1, 'Alice Johnson',   'Chicago',     'alice@example.com'),
    (2, 'Brian Smith',     'Miami',       'brian@example.com'),
    (3, 'Carla Rodriguez', 'New York',    'carla@example.com'),
    (4, 'David Lee',       'Chicago',     'david@example.com'),
    (5, 'Emily Davis',     'Los Angeles', 'emily@example.com'),
    (6, 'Frank Moore',     'Miami',       'frank@example.com'),
    (7, 'Grace Kim',       'Seattle',     'grace@example.com'),
    (8, 'Henry Thompson',  'Boston',      'henry@example.com');

INSERT INTO products (product_id, product_name, category, price) VALUES
    (1, 'Laptop Pro 14',               'Electronics', 1400.00),
    (2, 'Noise-Cancelling Headphones', 'Accessories',  180.00),
    (3, '4K Monitor',                  'Electronics',  320.00),
    (4, 'Mechanical Keyboard',         'Accessories',   95.00),
    (5, 'Wireless Mouse',              'Accessories',   45.00),
    (6, 'External SSD 1TB',            'Storage',      210.00);

INSERT INTO orders (order_id, customer_id, product_id, order_date, quantity, total) VALUES
    ( 1, 1, 1, '2024-01-12', 1, 1400.00),
    ( 2, 2, 2, '2024-01-18', 2,  360.00),
    ( 3, 3, 3, '2024-02-03', 1,  320.00),
    ( 4, 1, 4, '2024-02-10', 1,   95.00),
    ( 5, 4, 1, '2024-02-15', 1, 1400.00),
    ( 6, 5, 6, '2024-03-01', 1,  210.00),
    ( 7, 6, 5, '2024-03-05', 3,  135.00),
    ( 8, 7, 2, '2024-03-10', 1,  180.00),
    ( 9, 8, 3, '2024-03-15', 2,  640.00),
    (10, 3, 1, '2024-03-20', 1, 1400.00);
