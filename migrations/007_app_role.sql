-- 007_app_role.sql
-- Root cause fix: supabase `postgres` role has BYPASSRLS, so all RLS
-- (including FORCE, migrations 005/006) was bypassed for app traffic.
-- Create a least-privilege app role WITHOUT bypassrls; app pool connects
-- as paraiq_app; migrations continue to run as postgres.
-- NOTE: password is set out-of-band (ALTER ROLE ... PASSWORD), never committed.

CREATE ROLE paraiq_app LOGIN NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;

GRANT USAGE ON SCHEMA public TO paraiq_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO paraiq_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO paraiq_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO paraiq_app;

-- Future objects created by postgres (migrations) are auto-granted:
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO paraiq_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO paraiq_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO paraiq_app;

-- App startup uses CREATE TABLE IF NOT EXISTS init functions throughout;
-- Postgres requires CREATE on the schema even when the table exists.
-- Granting CREATE preserves the critical property (NOBYPASSRLS) while
-- matching the codebase's self-initializing design. Future cleanup: strip
-- vestigial init-CREATEs from startup and revoke this.
GRANT CREATE ON SCHEMA public TO paraiq_app;

-- postgres must be a member of paraiq_app to transfer ownership to it
-- (Supabase postgres is not a true superuser). Benign: admin can act as
-- app role, not vice versa.
GRANT paraiq_app TO postgres;

-- Startup init functions also run owner-requiring DDL (ALTER TABLE / CREATE
-- INDEX) on existing tables. Ownership transferred to paraiq_app: safe because
-- FORCE ROW LEVEL SECURITY (migration 005) subjects owners to policies, and
-- paraiq_app has NOBYPASSRLS. Applied via script: ALTER TABLE/SEQUENCE
-- ... OWNER TO paraiq_app for all objects in schema public.
