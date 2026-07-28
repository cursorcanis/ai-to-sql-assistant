# Restructure Tracker

Working log for the restructuring of **AI SQL Assistant**. Update the status boxes as
work lands. Anything marked "proposed" is not yet agreed.

---

## 1. Starting point (as of 2026-07-27)

```
ai-sql-assistant/
├── app.py              # 102 lines: config, prompt, safety, DB access, and UI
└── sample_database.db  # SQLite: customers(8), products(6), orders(10)
```

No git repo, no `requirements.txt`, no `.env.example`, no README, no tests.

**What `app.py` does today**

| Lines | Responsibility |
| --- | --- |
| 1–10 | Load `.env`, construct module-level `OpenAI` client |
| 13–16 | `is_safe_sql` — substring blocklist of DDL/DML keywords |
| 19–50 | `generate_sql_from_question` — hardcoded schema in system prompt, strips ``` fences |
| 53–66 | `run_sql_query` — opens `sample_database.db`, returns `(rows, columns)` or `(None, error)` |
| 70–101 | Streamlit form, safety gate, result rendering |

**Database schema** (matches the prompt text, for now)

- `customers(CustomerID PK, Name, City, Email)`
- `products(ProductID PK, ProductName, Category, Price)`
- `orders(OrderID PK, CustomerID FK, ProductID FK, OrderDate TEXT, Quantity, Total)`

---

## 2. Issues found while reading

Ordered roughly by how much they'd hurt.

### Correctness / safety

- [ ] **`is_safe_sql` is a substring match, not a SQL check.** `"SELECT * FROM products
      WHERE Category='UPDATED'"` is rejected; `"SELECT ... ; DROP TABLE customers"` is
      also rejected but only by luck of the wordlist. A column named `Created` would
      trip `CREATE`. Should parse the statement, require a single statement, and require
      it to start with `SELECT`/`WITH`.
- [ ] **Connection is read-write.** Even with the filter, the DB should be opened
      read-only (`file:sample_database.db?mode=ro` with `uri=True`) so a bypass can't
      mutate data.
- [ ] **`run_sql_query` overloads its return value.** On error it returns
      `(None, "SQL error: ...")` — a string where callers expect a column list. The UI
      then prints `Error running SQL: SQL error: ...` (doubled prefix, line 97).
      Raise instead, or return a small result type.
- [ ] **No `cursor.description` guard.** A statement returning no result set makes
      line 60 raise `TypeError`, caught only by the broad `except`.
- [ ] **Empty question is sent to the model.** Submitting the blank form calls the API.
- [ ] **API key never validated.** A missing `OPENAI_API_KEY` fails deep inside the
      request instead of at startup with a clear message.
- [ ] **Bare `except Exception`** swallows programming errors alongside SQL errors.

### Structure

- [ ] **Everything lives in one module.** No seam to unit-test SQL generation or the
      safety check without importing Streamlit and constructing an OpenAI client at
      import time (line 10 runs on import).
- [ ] **Schema is duplicated** — hardcoded in the prompt string (lines 28–30) and in
      the actual DB. They agree today; nothing keeps them agreeing. Introspect
      `sqlite_master` instead.
- [ ] **DB path and model name are string literals** buried in functions.
- [ ] **Fence-stripping is hand-rolled** (lines 42–48) and only handles the first
      fenced block.

### Ergonomics

- [ ] **No dependency manifest.** `streamlit`, `openai`, `python-dotenv` are implied.
- [ ] **No README / `.env.example`.**
- [ ] **Not under version control** — nothing to diff a restructure against.
- [ ] **Dataframe built via dict comprehension** (line 100) rather than passing rows
      to pandas; loses dtypes and reads awkwardly.
- [ ] **Course-artifact comments** (`# --- NEW (03_01) ---`, `# ← updated per 03_01`)
      are noise in a standalone project.

---

## 3. Proposed target structure

Not yet confirmed — see open questions below.

```
ai-sql-assistant/
├── app.py                  # Streamlit UI only
├── sql_assistant/
│   ├── __init__.py
│   ├── config.py           # env loading, model name, DB path, fail-fast validation
│   ├── schema.py           # introspect SQLite -> schema text for the prompt
│   ├── generator.py        # question -> SQL via OpenAI
│   ├── safety.py           # statement validation (SELECT-only, single statement)
│   └── database.py         # read-only connection, query execution
├── tests/
│   ├── test_safety.py
│   └── test_schema.py
├── sample_database.db
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 4. Change log

Append one row per landed change.

| # | Date | Change | Files | Status |
| --- | --- | --- | --- | --- |
| 0 | 2026-07-27 | Read existing code, wrote this tracker | `RESTRUCTURE.md` | done |
| 1 | 2026-07-27 | Switched provider OpenAI → OpenRouter | `app.py` | done |
| 2 | 2026-07-27 | Added secrets/dependency scaffolding | `.env`, `.env.example`, `.gitignore`, `requirements.txt` | done |
| 3 | 2026-07-27 | Verified provider switch against live API | — | done |
| 4 | 2026-07-27 | `git init`, initial commit, pushed to GitHub | all | done |
| 5 | 2026-07-27 | Local end-to-end test via Streamlit `AppTest` | — | done |
| 6 | 2026-07-27 | Fixed safety check, empty input, error handling | `app.py` | done |
| 7 | 2026-07-27 | Bounded API timeout, surfaced API errors | `app.py` | done |
| 8 | 2026-07-27 | Untracked `.claude/` tooling config | `.gitignore` | done |
| 9 | 2026-07-27 | Port SQLite → Supabase Postgres | `app.py`, `migrations/`, `requirements.txt`, `.env.example` | done |
| 10 | 2026-07-27 | Migrations applied to Supabase, verified | `scripts/`, `migrations/` | done |
| 11 | 2026-07-27 | Removed `sample_database.db` | — | done |
| 12 | 2026-07-27 | `@claude` GitHub Actions workflow | `.github/`, `CLAUDE.md` | done |
| 13 | 2026-07-27 | Model now explains the query before returning it | `app.py` | done |
| 14 | 2026-07-27 | Migration ledger; each file applies once | `scripts/run_migrations.py` | done |
| 15 | 2026-07-27 | 17-table analytics star schema + 326k rows | `migrations/003`, `scripts/seed_data.py` | done |
| 16 | 2026-07-27 | Prompt schema introspected instead of hardcoded | `app.py` | done |

### Notes on changes #14–16 — analytics schema

**Ledger.** `schema_migrations(filename, checksum, applied_at)`. Files run once;
re-running is a no-op. This mattered because `001` drops and recreates its tables —
a second run would have destroyed data. Editing an applied file warns rather than
silently diverging. `--status` lists state, `--force <file>` re-applies deliberately.

**Schema.** 17 tables, deliberately shaped for advanced practice:

| Technique | Where it lives |
| --- | --- |
| Recursive CTEs | `employees.manager_id` (5 levels), `categories.parent_category_id` (3) |
| Window functions | 6 years of orders with real trend and seasonality |
| Temporal joins | `product_price_history` — type-2 SCD, `valid_from`/`valid_to` |
| Many-to-many | `order_items`, `campaign_customers` |
| Multi-grain facts | `order_items`, `returns`, `payments`, `inventory_snapshots` |
| Time intelligence | `dim_date` with fiscal year/quarter |
| Geography | `regions → countries → cities` with lat/long for Power BI maps |

**Sizing.** The binding limit is Supabase's ~500 MB, not Streamlit — Streamlit
Cloud hosts the app (~1 GB RAM) and stores nothing. Seeded at 326,417 rows /
**47 MB**, about 10% of the free tier.

Data is generated, not committed: 326k rows of `INSERT` would be an unreviewable
diff. `random.seed(42)` makes it reproducible. It is deliberately non-uniform —
measured on the result, December 2023 is ~3x June 2023, and revenue grows ~12%
a year, so seasonality and YoY queries find real signal.

**Introspection.** The prompt now calls `describe_schema()` rather than carrying a
hardcoded schema — closing the duplication issue from §2. Foreign keys are read
from `pg_catalog`: `information_schema.constraint_column_usage` only shows
constraints on tables the role *owns*, and the read-only role owns nothing, so it
returned **zero** foreign keys on the first attempt.

**Row cap.** `MAX_DISPLAY_ROWS = 1000`, enforced with `fetchmany` rather than
`fetchall`. `order_items` holds 136k rows; materialising that would exhaust the
app's memory on Streamlit Cloud.

Verified end to end: monthly revenue with running total and MoM change
(`SUM(SUM(...)) OVER`, `LAG`), a recursive org-chart depth query over all 200
employees, and a three-fact comparison where the model correctly aggregated each
fact in its own CTE before joining instead of double counting.

### Notes on change #13 — explanation before SQL

The prompt now asks for a plain-English explanation followed by the statement.
That alone would have broken the app: `is_safe_sql` requires the query to *start*
with `SELECT`/`WITH`, so prose in front of it would fail every request, and
`st.code(..., language="sql")` would syntax-highlight the prose.

`generate_sql_from_question` therefore returns `(explanation, sql)` instead of a
bare string. `split_explanation_and_sql` cuts at the first line matching
`^\s*(SELECT|WITH)\b`; everything above is the explanation. If no statement line
is found the whole reply is returned as SQL, so `is_safe_sql` rejects it and the
user sees what the model actually said rather than a silent failure.

Fence-stripping stays — the prompt asks for no markdown fences, but models add
them anyway — and now keeps the prose before the fence as the explanation.

`max_tokens` raised 500 → 900 to fit both parts.

Side effect worth knowing: "Delete all customers from Boston" now returns a
`SELECT` of Boston customers rather than a `DELETE`, so it no longer trips the
safety error. Both safety layers are unchanged and still verified; the model is
simply interpreting the request as a read.

### Notes on change #9 — Postgres migration

Decision: Supabase, porting the existing 24 rows so results match what was tested.

**Columns renamed to snake_case.** Postgres folds unquoted identifiers to lowercase, so
`CustomerID` would need double-quoting in every generated query — an unreliable thing to
ask of an LLM. `customer_id` works unquoted.

**Connection pooling added.** Streamlit reruns the script on every interaction; the old
connect-per-query pattern was free with SQLite but would exhaust a free-tier Postgres
connection limit. One `@st.cache_resource` engine now, `pool_size=2`, `pool_pre_ping`
for connections the server dropped while idle.

**`exec_driver_sql`, not `text()`** — `text()` reads `:` as a bind parameter and would
break on casts like `::int`.

**Secrets now read from `st.secrets` first, then `os.getenv`.** Streamlit Cloud has no
`.env`; local dev has no `secrets.toml`. Same code path works in both.

**Read-only enforcement moved into the database** (`migrations/002_readonly_role.sql`):
`GRANT SELECT` only, no `CREATE`, `statement_timeout = 10s`. `is_safe_sql` stays as the
friendly first check, but the role is what actually guarantees it.

### Notes on change #10 — applying the migrations

Four connection-string problems, worth recording because none are obvious:

1. **A `#` in the password silently truncates the URL.** `#` starts a URI fragment, so
   the host and port were being discarded. Keep Supabase passwords alphanumeric.
2. **`db.<ref>.supabase.co` does not resolve.** Supabase's direct-connection host is
   IPv6-only on new projects. The pooler hosts are IPv4 — use those.
3. **The pooler needs the project ref in the username**: `postgres.<ref>`, not
   `postgres`. A plain username gives an authentication error that looks like a wrong
   password. (Diagnosed by connecting with a deliberately bogus ref: that returns
   `ENOTFOUND tenant/user`, proving the real failure was the password.)
4. **Session pooler (5432) for migrations, transaction pooler (6543) for the app.**
   DDL wants a real session.

`002` also had to change twice: Supabase's `postgres` user is *not* a true superuser, so
neither `DROP ROLE` (grants depend on it) nor `DROP OWNED BY` (not a member of the role)
works. It now updates the password in place via a `DO` block if the role already exists.

The role password is substituted into the SQL at run time from
`SQL_ASSISTANT_RO_PASSWORD`, so `migrations/002_readonly_role.sql` stays safe to commit.

**Read-only role verified** — all five refused at the database level:

| Attempted | Result |
| --- | --- |
| `DELETE FROM customers` | permission denied for table customers |
| `INSERT INTO customers` | permission denied for table customers |
| `UPDATE products` | permission denied for table products |
| `CREATE TABLE evil` | permission denied for schema public |
| `DROP TABLE orders` | must be owner of table orders |

`rolsuper = false`, `rolcreatedb = false`, `SELECT` works.

**App verified against Postgres**, six cases: top spender returns
`Carla Rodriguez, 1720.00` — identical to the SQLite result. The model emits snake_case
unprompted and used `DATE_TRUNC` for the monthly query, confirming the dialect change.

### Notes on change #11

`sample_database.db` deleted; nothing references it now that the DB layer is Postgres.
Recoverable from git history if ever needed.

Still to do: deploy to Streamlit Cloud (secrets go in the app's Secrets panel, not `.env`),
and delete `SUPABASE_ADMIN_URL` from `.env` now that migrations have run.

### Notes on change #7 — the "stuck in a loop" report

Not a loop. Streamlit dims stale elements while re-running, so a spinner sitting above
the *previous* run's output reads as if the app is cycling. There is no cycle in the
script — it runs top to bottom once per submit.

Chasing it did surface a real bug: the OpenAI SDK defaults to a **600s read timeout with
2 retries**. A stalled or rate-limited call could hold the spinner for ~30 minutes with
no error, indistinguishable from a hang. OpenRouter's free tier (~20 req/min) returns 429
under the kind of load our testing generated.

Now `timeout=30.0`, `max_retries=1`, `max_tokens=500`, with `APITimeoutError`,
`RateLimitError` and `APIError` each caught and shown as an actionable message.
Measured latency for reference: 0.6s–3.5s per call.

**Confirmed working in the browser** by the user, all four cases: blank input, destructive
request, normal question, zero-match question.

### Notes on change #5 — local test run

Server booted on :8502 (`/_stcore/health` → `ok`, `GET /` → 200). App driven headlessly
with `streamlit.testing.v1.AppTest`, which executes the real script and real widgets.

**Three realistic questions — all correct**, valid SQL and correct result sets:
top spender (`Carla Rodriguez, 1720.0`), Electronics products (2 rows), orders per
city (6 rows). No exceptions, no errors.

**Destructive request blocked**: "Delete all customers from Boston" generated
`DELETE FROM customers WHERE City='Boston'` and the safety gate stopped it.

**Two §2 issues confirmed by test, still unfixed:**

- *Empty input*: submitting a blank form still calls the API. The model invents an
  unrelated query (a HAVING COUNT > 5 join) and the user gets a confusing empty table.
- *`is_safe_sql` false positives*: direct probing shows it blocks legitimate read-only
  queries — `WHERE Status = 'UPDATED'` and `LIKE '%CREATE%'` are both rejected. It also
  "catches" `SELECT ...; DROP TABLE orders;` only because *DROP* is in the wordlist, not
  because it recognises the statement chain. A `SELECT`-only + single-statement parse
  is the actual fix.

### Notes on change #6 — safety and input handling

Closes five §2 items.

**`is_safe_sql` rewritten as an allowlist.** String literals and comments are blanked
first (so `WHERE Status = 'UPDATED'` is judged on its SQL, not its data), the query must
be exactly one statement, and it must begin with `SELECT` or `WITH`. The forbidden-verb
regex stays as defence in depth, now word-anchored and extended with `ATTACH`, `PRAGMA`,
`VACUUM`, `TRUNCATE`, `REPLACE`, `GRANT`, `REVOKE`, `REINDEX`.

Verified 14/14 on a table of allow/block cases: the two legitimate queries the old
version rejected now pass, and chained statements, comment-hidden statements,
`ATTACH DATABASE`, and `PRAGMA writable_schema` are all blocked.

**Connection is read-only** — `file:...?mode=ro` with `uri=True`. Confirmed by attempting
a `DELETE` through it: *"attempt to write a readonly database"*, 8 customers intact. This
is the real protection; `is_safe_sql` is now the friendly first line, not the only one.

**Other fixes:** empty question short-circuits before the API call; empty model response
handled; `cursor.description is None` guarded; `except Exception` narrowed to
`sqlite3.Error`; `connection.close()` moved to `finally`; doubled "Error running SQL: SQL
error:" prefix removed; zero-row results show a message instead of an empty grid;
spinner added during generation.

Re-driven through `AppTest`: blank input warns with no API call, `DELETE` request blocked,
normal question returns data, no-match question reports cleanly.

### Notes on change #1 — provider switch

Kept the official `openai` SDK: OpenRouter is OpenAI-API-compatible, so only the
base URL, key, and model name changed. No client library swap needed.

- `OPENAI_API_KEY` → `OPENROUTER_API_KEY`
- `base_url="https://openrouter.ai/api/v1"`
- `gpt-4o-mini` → `nvidia/nemotron-3-super-120b-a12b:free`, lifted to a `MODEL` constant
- **Reasoning disabled** via `extra_body={"reasoning": {"enabled": False}}`. This model
  has `default_enabled: true` for reasoning but `mandatory: false`. Left on, chain-of-thought
  would land in the response body and break the fence-stripping in
  `generate_sql_from_question`.
- **`temperature=0`**. The model's default is `1.0`; SQL generation wants determinism.
- Fail-fast check for a missing key (closes one item in §2).
- `message.content or ""` guards a `None` content response.

Still open from §2, unchanged by this work: the broken `is_safe_sql` substring check,
the read-write DB connection, and the overloaded `run_sql_query` return value.

### Notes on change #3 — live verification

End-to-end test with a real key: "Which customers spent the most in total?" produced a
correct `JOIN` + `GROUP BY` query with no markdown fences, which then ran against
`sample_database.db` and returned `Carla Rodriguez, 1720.0`. The `reasoning` field on the
response came back empty, confirming `enabled: False` takes effect.

### Notes on change #4 — version control

`git init -b main`, remote `origin` →
`https://github.com/cursorcanis/ai-to-sql-assistant.git`.

`.gitignore` was authored **before** the first commit, so `.env` was never staged.
Verified post-push: `.env` is untracked, and `git log -p --all` contains zero key matches.

Six files tracked: `.env.example`, `.gitignore`, `RESTRUCTURE.md`, `app.py`,
`requirements.txt`, `sample_database.db`.

---

## 5. Open questions

1. **How far do we go?** Light cleanup of `app.py` in place, or the package split above?
2. **`git init` first?** Strongly recommended before moving files.
3. **Tests — yes?** If so, `pytest`; the safety check and schema introspection are the
   parts worth covering.
4. **Keep the fixed sample DB**, or make the DB path configurable so it points at any
   SQLite file?
5. **Stay on `gpt-4o-mini`/OpenAI**, or is the provider open for discussion?
