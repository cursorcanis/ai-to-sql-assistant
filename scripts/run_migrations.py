"""Apply the SQL files in migrations/ to Supabase, each exactly once.

Reads SUPABASE_ADMIN_URL from .env — the superuser connection string, needed
only to create tables and roles. The app never uses it; it connects as the
read-only role instead.

Applied migrations are recorded in a schema_migrations table, so re-running is
safe: a file that has already been applied is skipped. That matters because
001 drops and recreates its tables, which would destroy data on a second run.

Usage:
    python scripts/run_migrations.py           # apply anything not yet applied
    python scripts/run_migrations.py --status  # list applied / pending, run nothing
    python scripts/run_migrations.py --force 003_analytics_schema.sql
                                               # re-apply one file deliberately

Nothing here prints the connection string.
"""

import os
import sys
import glob
import hashlib
import psycopg2
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_ADMIN_URL")
if not url:
    sys.exit("SUPABASE_ADMIN_URL is not set in .env — see .env.example.")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def substitute_secrets(sql, name):
    """Inject values that must not live in a tracked file.

    Postgres has no bind parameters for CREATE ROLE, so this is string
    substitution — but the value comes from .env, never from user input.
    """
    if "${RO_PASSWORD}" not in sql:
        return sql

    password = os.getenv("SQL_ASSISTANT_RO_PASSWORD")
    if not password:
        print(f"SKIP {name} — SQL_ASSISTANT_RO_PASSWORD is not set in .env")
        return None
    if "'" in password:
        sys.exit("SQL_ASSISTANT_RO_PASSWORD must not contain a single quote.")
    return sql.replace("${RO_PASSWORD}", password)


connection = psycopg2.connect(url)
connection.autocommit = True

try:
    with connection.cursor() as cursor:
        cursor.execute(LEDGER)
        cursor.execute("SELECT filename, checksum FROM schema_migrations")
        applied = dict(cursor.fetchall())

    forced = sys.argv[sys.argv.index("--force") + 1] if "--force" in sys.argv else None
    files = sorted(glob.glob(os.path.join(ROOT, "migrations", "*.sql")))
    if not files:
        sys.exit("No migration files found.")

    if "--status" in sys.argv:
        print(f"{'migration':<34} status")
        for path in files:
            name = os.path.basename(path)
            digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
            if name not in applied:
                state = "PENDING"
            elif applied[name] != digest:
                state = "APPLIED (file changed since)"
            else:
                state = "applied"
            print(f"  {name:<32} {state}")
        raise SystemExit(0)

    ran = 0
    for path in files:
        name = os.path.basename(path)
        raw = open(path, "rb").read()
        digest = hashlib.sha256(raw).hexdigest()

        if name in applied and name != forced:
            if applied[name] != digest:
                print(f"WARN {name} — already applied but the file has changed "
                      f"since; add a new migration rather than editing this one.")
            else:
                print(f"skip {name} — already applied")
            continue

        sql = substitute_secrets(raw.decode("utf-8"), name)
        if sql is None:
            continue

        with connection.cursor() as cursor:
            cursor.execute(sql)
            cursor.execute(
                "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s) "
                "ON CONFLICT (filename) DO UPDATE SET checksum = EXCLUDED.checksum, "
                "applied_at = now()",
                (name, digest),
            )
        print(f"OK   {name}")
        ran += 1

    print(f"\n{ran} migration(s) applied.")

    # Report what now exists, so the run is verified rather than assumed.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name <> 'schema_migrations' "
            "ORDER BY table_name"
        )
        tables = [r[0] for r in cursor.fetchall()]
        print(f"\n{len(tables)} tables:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table:26} {cursor.fetchone()[0]:>8,} rows")

finally:
    connection.close()
