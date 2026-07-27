-- Create the read-only role the app connects as.
--
-- This is the structural replacement for the keyword blocklist: even if a
-- generated query slips past is_safe_sql, the database itself will refuse to
-- execute a write. The app should NEVER connect as the postgres superuser.
--
-- The password is NOT stored in this file. scripts/run_migrations.py replaces
-- ${RO_PASSWORD} below with the value of SQL_ASSISTANT_RO_PASSWORD from .env,
-- so the secret lives only there and in Streamlit Cloud Secrets. That keeps
-- this file safe to commit.

-- Re-runnable without dropping: Supabase's "postgres" user is not a true
-- superuser and may not drop objects owned by another role, so update the
-- password in place if the role already exists.
DO $$
DECLARE
    pw text := '${RO_PASSWORD}';
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sql_assistant_ro') THEN
        EXECUTE format('ALTER ROLE sql_assistant_ro WITH LOGIN PASSWORD %L', pw);
    ELSE
        EXECUTE format('CREATE ROLE sql_assistant_ro WITH LOGIN PASSWORD %L', pw);
    END IF;
END
$$;

-- Allow connecting and reading, nothing else.
GRANT CONNECT ON DATABASE postgres TO sql_assistant_ro;
GRANT USAGE ON SCHEMA public TO sql_assistant_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sql_assistant_ro;

-- Cover tables created later too.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO sql_assistant_ro;

-- Explicitly deny table creation in the public schema.
REVOKE CREATE ON SCHEMA public FROM sql_assistant_ro;

-- Cap runaway queries at 10 seconds so one bad generated query cannot pin the
-- database (relevant on a free tier with limited connections).
ALTER ROLE sql_assistant_ro SET statement_timeout = '10s';

-- Verify afterwards:
--   SELECT rolname, rolcanlogin, rolsuper, rolcreatedb
--     FROM pg_roles WHERE rolname = 'sql_assistant_ro';
-- Expect: rolcanlogin = t, rolsuper = f, rolcreatedb = f
