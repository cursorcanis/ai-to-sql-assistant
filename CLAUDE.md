# AI SQL Assistant

Streamlit app that turns plain-English questions into SQL, runs them against a
Supabase Postgres database, and shows the results.

## Architecture

Single module, `app.py`:

- **Model access** — the `openai` SDK pointed at OpenRouter's compatible
  endpoint (`base_url="https://openrouter.ai/api/v1"`). There is no OpenAI
  account involved; the SDK is just a client. Model is
  `nvidia/nemotron-3-super-120b-a12b:free`.
- **Database** — SQLAlchemy engine over `psycopg2`, one pooled engine cached
  with `@st.cache_resource`.
- **Migrations** — plain SQL in `migrations/`, applied by
  `scripts/run_migrations.py`.

## Schema

17 tables, a star schema built for practising advanced SQL and Power BI
modelling. **Do not hardcode it anywhere** — `describe_schema()` introspects it
at runtime and feeds it to the prompt, so the two cannot drift apart.

Dimensions: `dim_date`, `regions` → `countries` → `cities`, `employees`
(self-referencing `manager_id`), `categories` (self-referencing
`parent_category_id`), `suppliers`, `products`, `product_price_history`
(type-2 SCD), `customers`, `campaigns`, `campaign_customers` (bridge).

Facts, at four different grains: `order_items` (line), `returns` (line),
`payments` (order), `inventory_snapshots` (product-month). Aggregate each
separately before combining — joining them directly double counts.

~326k rows, 47 MB. Regenerate with `python scripts/seed_data.py`
(deterministic: `random.seed(42)`).

## Things that will bite you

These were all discovered the hard way; please don't undo them.

- **Reasoning is disabled** on the model via
  `extra_body={"reasoning": {"enabled": False}}`. It defaults to *on*, and the
  chain of thought lands in the response body and breaks fence-stripping.
- **`temperature=0`.** The model's own default is 1.0.
- **`timeout=30, max_retries=1` on the client.** The SDK defaults to a 600s
  read timeout with 2 retries — a rate-limited call otherwise hangs the UI for
  half an hour with no error.
- **Columns are snake_case deliberately.** Postgres folds unquoted identifiers
  to lowercase; mixed-case names would need double-quoting in every generated
  query, which an LLM will not do reliably.
- **Foreign keys come from `pg_catalog`, not `information_schema`.**
  `information_schema.constraint_column_usage` only reveals constraints on
  tables the current role *owns*. The app connects as a role that owns nothing,
  so it silently returns zero foreign keys.
- **Results are capped at `MAX_DISPLAY_ROWS` via `fetchmany`.** `order_items`
  has 136k rows and Streamlit Cloud gives the app ~1 GB; never materialise a
  full result set.
- **Migrations are tracked in `schema_migrations`** and each file runs once.
  `001` drops and recreates tables, so re-running it would destroy data. Add a
  new numbered file rather than editing an applied one.
- **`exec_driver_sql`, not `text()`.** `text()` treats `:` as a bind parameter
  and breaks on casts like `::int`.
- **Supabase connection strings**: the pooler requires the project ref in the
  username (`sql_assistant_ro.<ref>`), and the direct host
  (`db.<ref>.supabase.co`) is IPv6-only and will not resolve on most networks.
  Use the pooler host. Keep passwords alphanumeric — a `#` truncates the URL at
  the fragment marker.

## Safety model

Two independent layers, and the second is the one that matters:

1. `is_safe_sql()` — an allowlist. Blanks string literals and comments, then
   requires exactly one statement beginning with `SELECT` or `WITH`. This is a
   friendly first error, not a security boundary.
2. **The database role.** The app connects as `sql_assistant_ro`, which holds
   `SELECT` only, cannot create tables, and has a 10s `statement_timeout`.
   Verified: `DELETE`, `INSERT`, `UPDATE`, `CREATE TABLE` and `DROP TABLE` are
   all refused by Postgres.

Never suggest connecting as the `postgres` superuser. `SUPABASE_ADMIN_URL` is
for migrations only and must never reach a deployed environment.

## Configuration

Read via `get_secret()`, which checks `st.secrets` then environment variables,
so the same code runs locally (`.env`) and on Streamlit Cloud (Secrets panel).

- `OPENROUTER_API_KEY`
- `DATABASE_URL` — read-only role, transaction pooler, port 6543
- `SUPABASE_ADMIN_URL`, `SQL_ASSISTANT_RO_PASSWORD` — migrations only

## Note for CI

This workflow has **no** `OPENROUTER_API_KEY` or `DATABASE_URL`, by design — a
comment-triggered job should not hold database credentials. You can read code,
reason about it, and propose diffs, but you cannot run the app or query the
database here. Say so rather than guessing at runtime behaviour.

`RESTRUCTURE.md` is the running log of what changed and why.
