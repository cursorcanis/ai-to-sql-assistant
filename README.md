# AI SQL Assistant

Ask a question in plain English, get back an explanation, the SQL, and the result table. The app runs against a 17-table analytics star schema on Postgres. Built with Python and Streamlit.

## What it does

1. Reads the live database schema (tables, columns, foreign keys) and gives it to the model, so the prompt cannot drift from the database.
2. Asks an LLM (via OpenRouter) to explain its approach and write one query.
3. Checks the query, runs it as a read-only database role, and shows up to 1,000 rows.

## The database

A synthetic retail dataset built for practicing advanced SQL and Power BI modeling: **17 tables, ~326K rows, six years of orders (2019 to 2024)**, generated deterministically by `scripts/seed_data.py` (`random.seed(42)`).

| Technique | Where it lives |
| --- | --- |
| Recursive CTEs | `employees.manager_id` (5 levels), `categories.parent_category_id` (3 levels) |
| Window functions | Six years of orders with trend and seasonality |
| Temporal joins | `product_price_history`, a type-2 slowly changing dimension (`valid_from` / `valid_to`) |
| Many-to-many | `order_items`, `campaign_customers` (bridge) |
| Multi-grain facts | `order_items` (line), `returns` (line), `payments` (order), `inventory_snapshots` (product-month) |

The four fact tables sit at different grains, so each one has to be aggregated separately before combining. Joining them directly double counts.

## Safety model

The app executes SQL written by a model, so it assumes that SQL can be wrong. There are three layers, and the database is the one that counts:

1. **Statement allowlist** (`is_safe_sql`). Blanks out comments and string literals, rejects anything that isn't exactly one statement starting with `SELECT` or `WITH`, then rejects write verbs hidden in subqueries. This gives a friendly first error. It is not the security boundary.
2. **Least-privilege role** (`migrations/002`). The app connects as `sql_assistant_ro`, which holds `SELECT` only, cannot create tables, and has a 10-second `statement_timeout`. Verified: `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE` and `DROP TABLE` are all refused by Postgres.
3. **Read-only transaction.** Every query runs inside `SET TRANSACTION READ ONLY`.

Separately, `migrations/004` revokes all access from Supabase's public API roles (`anon`, `authenticated`) and enables row-level security on every table. The app never uses that API, so closing it costs nothing.

## Engineering notes

- **Bounded results.** Rows are fetched with `fetchmany(1001)` so a `SELECT *` over the 136K-row `order_items` table never loads fully into memory.
- **Bounded API calls.** 30-second timeout, one retry. The SDK default (600 s, two retries) can hang the UI for a long time with no error.
- **Deterministic output.** `temperature=0`, and model reasoning is turned off so its chain of thought doesn't leak into the reply.
- **Foreign keys from `pg_catalog`.** `information_schema` only shows constraints on tables the current role owns. The read-only role owns nothing, so `information_schema` would return zero foreign keys.
- **Tracked migrations.** `scripts/run_migrations.py` records each file in a `schema_migrations` table with a checksum and applies it only once.

## Stack

Python · Streamlit · PostgreSQL (Supabase) · SQLAlchemy / psycopg2 · OpenAI SDK pointed at OpenRouter (`nvidia/nemotron-3-super-120b-a12b:free`)

## Run it locally

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in the values; comments explain each one
python scripts/run_migrations.py
python scripts/seed_data.py
streamlit run app.py
```

You need an OpenRouter API key and a Postgres database. `.env.example` covers the Supabase connection-string quirks (pooler username format, IPv6-only direct host).

## Repository

```
app.py                  Streamlit app: schema introspection, prompt, safety check, query runner
theme.py                UI styling
migrations/             Plain SQL, applied in order by scripts/run_migrations.py
scripts/seed_data.py    Deterministic data generator
RESTRUCTURE.md          Running log of what changed and why
```
