-- Create the read-only role the app connects as.
--
-- This is the structural replacement for the keyword blocklist: even if a
-- generated query slips past is_safe_sql, the database itself will refuse to
-- execute a write. The app should NEVER connect as the postgres superuser.
--
-- BEFORE RUNNING: replace CHANGE_ME_TO_A_STRONG_PASSWORD below with a real
-- password. Do not commit the edited version of this file -- put the password
-- only in .env (local) and Streamlit Cloud Secrets (deployed).

CREATE ROLE sql_assistant_ro WITH LOGIN PASSWORD 'CHANGE_ME_TO_A_STRONG_PASSWORD';

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
