"""Apply the SQL files in migrations/ to Supabase.

Reads SUPABASE_ADMIN_URL from .env — the superuser connection string, needed
only to create tables and the read-only role. The app itself never uses it;
remove the line from .env once the migrations have run.

Usage:
    python scripts/run_migrations.py            # apply 001 only
    python scripts/run_migrations.py --all      # apply every file in order

Nothing here prints the connection string.
"""

import os
import sys
import glob
import psycopg2
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_ADMIN_URL")
if not url:
    sys.exit("SUPABASE_ADMIN_URL is not set in .env — see .env.example.")

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
files = sorted(glob.glob(os.path.join(root, "migrations", "*.sql")))
if "--all" not in sys.argv:
    files = [f for f in files if os.path.basename(f).startswith("001")]

if not files:
    sys.exit("No migration files found.")

connection = psycopg2.connect(url)
connection.autocommit = True

try:
    for path in files:
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as handle:
            sql = handle.read()

        # Secrets are substituted at run time so they never live in a tracked
        # file. Postgres has no bind parameters for CREATE ROLE, hence string
        # substitution — the value comes from .env, not from user input.
        if "${RO_PASSWORD}" in sql:
            ro_password = os.getenv("SQL_ASSISTANT_RO_PASSWORD")
            if not ro_password:
                print(f"SKIP {name} — SQL_ASSISTANT_RO_PASSWORD is not set in .env")
                continue
            if "'" in ro_password:
                sys.exit("SQL_ASSISTANT_RO_PASSWORD must not contain a single quote.")
            sql = sql.replace("${RO_PASSWORD}", ro_password)

        with connection.cursor() as cursor:
            cursor.execute(sql)
        print(f"OK   {name}")

    # Report what now exists, so the run is verified rather than assumed.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        tables = [r[0] for r in cursor.fetchall()]
        print("\ntables:", ", ".join(tables) or "(none)")

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table:12} {cursor.fetchone()[0]} rows")

finally:
    connection.close()
