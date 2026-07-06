# Incident write-up: The RLS That Wasn't (2026-07-06)

Raw material for PARAIQ_CASE_STUDY.md — narrative section drafted, evidence preserved.

## Timeline of discovery
- Fixing an unrelated dead frontend call (BriefView), added a routine cross-tenant
  check: thornton (firm_abc) GET /cases/4/brief — case 4 belongs to `default` firm.
  Expected 404. Got 200. Also reproduced on /cases/4 (case detail).
- Verified policy layer, in order, all correct:
  - pg_policies: `firm_id = current_firm_id()` isolation policy on all case tables
  - pg_class: relrowsecurity=t AND relforcerowsecurity=t (FORCE applied, migration 005)
  - current_firm_id() function: returns current_setting('app.current_firm_id', true);
    behavioral test under firm_abc context returned 'firm_abc' correctly
  - Yet: SELECT with app.current_firm_id='firm_abc' still returned the default-firm row
- Root cause layer 1: pg_roles showed the app's connection role (supabase `postgres`)
  has rolbypassrls=true. BYPASSRLS ignores RLS entirely — FORCE closes the *owner*
  bypass, not the *role attribute* bypass. Every policy on 67 forced tables was
  decorative for app traffic since the Postgres migration (May 2026).
- Root cause layer 2 (found during the fix): DATABASE_URL pointed at the Supavisor
  transaction-mode pooler (port 6543). set_config(is_local=false) tenant context is
  unsafe under transaction pooling — contexts can bleed across multiplexed
  connections. The RLS design requires session mode (port 5432).

## Fix (commit 7e08574, migration 007)
- Dedicated least-privilege role paraiq_app: LOGIN, NOBYPASSRLS, NOSUPERUSER
- Full DML grants + schema CREATE (app self-initializes tables at startup)
- Ownership of all 80 tables + 64 sequences transferred to paraiq_app — safe
  precisely because FORCE RLS subjects owners to policies and the role cannot bypass
- DSN: paraiq_app + port 5432 (session mode); migrations still run as postgres
- Collateral fix en route: brief pipeline had been dead since the Postgres migration
  (bare _get_db() calls never entered the context manager); resurrected, firm-scoped,
  auth-gated (was unauthenticated LLM spend)

## Verification matrix (post-fix)
- thornton reads default brief:   200 -> 404
- thornton reads default case:    200 -> 404
- maxwell(super) reads firm_abc:         404 (strict firm scoping even for super)
- thornton reads own brief:              200
- maxwell reads own brief:               200
- login with bad creds:                  401

## The lesson
Enabling a security control is not the same as verifying it enforces. The system
passed every configuration-level check — policies present, FORCE set, function
correct. Only an adversarial cross-tenant read exposed the gap. Isolation claims
are now gated on the test matrix, not on configuration inspection.
