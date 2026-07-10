-- Migration 009: client_portal_access token-based lookup
--
-- client_portal_access has FORCE RLS with a single ALL policy scoped by
-- firm_id (client_portal_access_isolation). That's correct for every normal
-- operation, but it creates a chicken-and-egg problem for the one place a
-- client portal token is looked up: the caller only has an opaque token,
-- not a firm_id, so no RLS context can be set before the lookup runs.
--
-- Fix: add a second, SELECT-only permissive policy that grants visibility
-- into exactly one row when the caller already holds that row's exact
-- access_token, via a session-local setting. Postgres OR's multiple
-- permissive policies for the same command, so this does not weaken the
-- existing firm-scoped policy for INSERT/UPDATE/DELETE, and it can only
-- ever expose the single row matching a token the caller must already
-- possess (32-byte, cryptographically random -- unguessable).

CREATE POLICY portal_token_lookup ON client_portal_access
  FOR SELECT
  USING (access_token = current_setting('app.portal_lookup_token', true));
