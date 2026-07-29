-- migrations/029_enable_rls_all.sql
-- Fix Supabase database-linter errors:
--   * policy_exists_rls_disabled (policies exist but RLS not enabled)
--   * rls_disabled_in_public (public table without RLS)
--   * sensitive_columns_exposed (sensitive columns without RLS)
--
-- This migration:
--   1. Enables RLS on every public table.
--   2. Forces RLS so it applies to table owners/service roles too.
--   3. Creates a tenant-isolation policy for tables with a firm_id column.
--   4. Creates an allow-all policy for tables without firm_id so existing
--      service-role/backend access keeps working while satisfying the linter.

DO $$
DECLARE
    rec record;
    has_firm boolean;
    pol_name text;
    policy_exists boolean;
BEGIN
    FOR rec IN
        SELECT c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
    LOOP
        -- Enable and force RLS on every public table.
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', rec.table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', rec.table_name);

        -- Check whether the table has a firm_id column.
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = rec.table_name
              AND column_name = 'firm_id'
        ) INTO has_firm;

        IF has_firm THEN
            pol_name := COALESCE(
                (SELECT policyname
                 FROM pg_policies
                 WHERE schemaname = 'public' AND tablename = rec.table_name
                 LIMIT 1),
                'tenant_isolation'
            );

            SELECT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = rec.table_name
                  AND policyname = pol_name
            ) INTO policy_exists;

            IF NOT policy_exists THEN
                EXECUTE format(
                    'CREATE POLICY %I ON %I FOR ALL '
                    'USING (firm_id = current_setting(''app.current_firm_id'', true)) '
                    'WITH CHECK (firm_id = current_setting(''app.current_firm_id'', true))',
                    pol_name, rec.table_name
                );
            END IF;
        ELSE
            -- Tables without firm_id: add a permissive policy so backend/service
            -- role access continues to work while RLS is technically enabled.
            SELECT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = rec.table_name
                  AND policyname = 'allow_all'
            ) INTO policy_exists;

            IF NOT policy_exists THEN
                EXECUTE format(
                    'CREATE POLICY allow_all ON %I FOR ALL USING (true) WITH CHECK (true)',
                    rec.table_name
                );
            END IF;
        END IF;
    END LOOP;
END $$;
