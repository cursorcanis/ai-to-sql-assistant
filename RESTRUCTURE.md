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
