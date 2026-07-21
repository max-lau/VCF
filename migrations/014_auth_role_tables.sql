-- 014_auth_role_tables.sql
-- Creates the role/permission tables referenced by backend/demo1/auth.py.
-- These were assumed by earlier migrations (005_force_rls.sql policy on
-- role_assignments) but never explicitly created.

-- ── Global roles lookup ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS roles (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    tier         INTEGER NOT NULL DEFAULT 3,
    default_open BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed roles that match backend/demo1/auth.py ROLE_TIER_MAP.
-- ON CONFLICT ensures this migration is idempotent.
INSERT INTO roles (name, tier, default_open) VALUES
    ('paraiq_super',    0, FALSE),
    ('firm_admin',      1, TRUE),
    ('admin',           1, TRUE),
    ('senior_attorney', 2, TRUE),
    ('associate',       3, TRUE),
    ('user',            3, TRUE),
    ('paralegal',       4, TRUE),
    ('client_viewer',   5, FALSE),
    ('billing_contact', 6, FALSE)
ON CONFLICT (name) DO UPDATE SET
    tier = EXCLUDED.tier,
    default_open = EXCLUDED.default_open;

-- ── Per-firm user-to-role assignments ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS role_assignments (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    role_id     INTEGER NOT NULL,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, firm_id)
);

CREATE INDEX IF NOT EXISTS idx_role_assignments_user_firm
    ON role_assignments(user_id, firm_id);
CREATE INDEX IF NOT EXISTS idx_role_assignments_firm
    ON role_assignments(firm_id);

ALTER TABLE role_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_assignments FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON role_assignments;
CREATE POLICY tenant_isolation ON role_assignments FOR ALL
    USING (firm_id = current_setting('app.current_firm_id', true))
    WITH CHECK (firm_id = current_setting('app.current_firm_id', true));

-- ── Module-level permissions per role ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS module_permissions (
    id         SERIAL PRIMARY KEY,
    role_id    INTEGER NOT NULL,
    module     TEXT NOT NULL,
    can_read   BOOLEAN DEFAULT FALSE,
    can_write  BOOLEAN DEFAULT FALSE,
    can_delete BOOLEAN DEFAULT FALSE,
    can_export BOOLEAN DEFAULT FALSE,
    can_admin  BOOLEAN DEFAULT FALSE,
    UNIQUE (role_id, module)
);

CREATE INDEX IF NOT EXISTS idx_module_permissions_role
    ON module_permissions(role_id);

-- ── Grants (uncomment and adjust role name to match migration 007_app_role.sql) ─
-- GRANT SELECT, INSERT, UPDATE, DELETE ON roles               TO app_role;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON role_assignments    TO app_role;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON module_permissions  TO app_role;
-- GRANT USAGE, SELECT ON SEQUENCE roles_id_seq                TO app_role;
-- GRANT USAGE, SELECT ON SEQUENCE role_assignments_id_seq     TO app_role;
-- GRANT USAGE, SELECT ON SEQUENCE module_permissions_id_seq   TO app_role;
