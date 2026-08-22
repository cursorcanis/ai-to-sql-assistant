-- Close the PostgREST path into this database.
--
-- Supabase flagged every table with rls_disabled_in_public ("Table publicly
-- accessible"). An audit confirmed the finding is real and complete: anon and
-- authenticated held SELECT, INSERT, UPDATE and DELETE on all 18 tables plus
-- USAGE on the schema, with row-level security disabled everywhere.
--
-- Why that is the whole story. Supabase exposes every table over PostgREST at
-- <project>.supabase.co/rest/v1/, authenticated by the anon key -- a JWT that
-- is DESIGNED to be public and ships inside client applications. The security
-- boundary is not the key, it is RLS. With RLS off and full grants in place,
-- anyone holding that key could read, rewrite or delete the entire star schema.
-- Nothing was protecting it except the key not having been looked up yet.
--
-- Why revoking outright is safe here, rather than writing read policies:
-- this app never uses the PostgREST API. requirements.txt has no supabase or
-- postgrest client; app.py builds a SQLAlchemy engine over psycopg2 and
-- connects as sql_assistant_ro (see 002), which holds only CONNECT, USAGE and
-- SELECT. The anon and authenticated roles are unused by this project, so
-- taking their access away cannot break the application.
--
-- Both halves are deliberate. The REVOKE removes today's access; ENABLE ROW
-- LEVEL SECURITY makes the tables deny-by-default so that a future GRANT --
-- whether run by hand or re-applied by Supabase tooling on a schema change --
-- does not silently reopen this. Belt and braces, because the failure is
-- silent and total.

-- ---------------------------------------------------------------------------
-- 1. Remove all access held by the public API roles.
-- ---------------------------------------------------------------------------

REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
REVOKE USAGE ON SCHEMA public FROM anon, authenticated;

-- Tables created after this migration would otherwise inherit the default
-- grants again. Note this only affects objects created by the role running
-- this file, which is why migration 003's own GRANT to sql_assistant_ro is
-- reasserted at the end.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. Enable RLS on every table in public, with no policies.
-- ---------------------------------------------------------------------------
-- RLS enabled + zero policies = deny all, for every role except the table
-- owner and roles with BYPASSRLS. That is exactly what is wanted: the app's
-- role reads through ordinary SELECT grants, and nothing reaches these tables
-- over the REST API at all.
--
-- Table owners bypass their own RLS, so the migration runner (superuser) and
-- anything owning these tables keep working unchanged.

DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Reassert the app role's access.
-- ---------------------------------------------------------------------------
-- Step 1 targeted anon and authenticated only, so these are unchanged in
-- practice. They are restated because this file is the one that would be
-- re-run if the public API is ever reopened by accident, and it should leave
-- the database in a fully working state on its own.

GRANT USAGE  ON SCHEMA public         TO sql_assistant_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sql_assistant_ro;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO sql_assistant_ro;

-- RLS applies to sql_assistant_ro too, and it does not own these tables, so
-- with no policies it would be denied everything and the app would return zero
-- rows for every question.
--
-- A read policy scoped to that one role is the fix. BYPASSRLS would also work
-- but requires a true superuser to grant, and Supabase's "postgres" is not
-- one -- the ALTER ROLE would fail partway through this migration. A policy
-- needs only table ownership, which the migration runner has.
--
-- Scoping TO sql_assistant_ro rather than TO public is the whole point: anon
-- and authenticated get no policy, so they stay denied even if someone
-- re-grants them table privileges later.
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS app_read_only ON public.%I', t);
        EXECUTE format(
            'CREATE POLICY app_read_only ON public.%I FOR SELECT TO sql_assistant_ro USING (true)',
            t
        );
    END LOOP;
END
$$;
