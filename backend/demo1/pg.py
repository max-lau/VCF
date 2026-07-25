"""
backend/demo1/pg.py  (ACP-VCF revision)
=======================================
Central Postgres module.

Fixes vs. original
  1. RLS TENANT CONTEXT BUG: _checkout() ran
         set_config('app.current_firm_id', %s, true)   -- is_local = TRUE
     and then immediately conn.commit(). A transaction-local setting dies
     when its transaction ends, so the commit erased the firm_id before any
     real query ran. Every subsequent query in the checkout executed with
     app.current_firm_id unset — meaning RLS either returned zero rows or,
     if the app connects as a role with BYPASSRLS/table-owner privileges,
     silently didn't filter at all (see docs/incident-2026-07-06-bypassrls.md).
     Fixed by using is_local = FALSE (session-level, survives commits) and
     resetting it on check-in so a pooled connection never leaks tenant
     context to the next request.
  2. SECRET UNIFICATION: TenantMiddleware decoded JWTs with SECRET_KEY
     (default "change_me") while main.py/auth sign and verify with
     JWT_SECRET_KEY. Unless both env vars were set identically, every decode
     here failed silently and firm_id fell back to "default". Masked in
     ACP-VCF because force_waw_tenant overwrites firm_id afterward, but the
     dead code path is now unified: JWT_SECRET_KEY, falling back to SECRET_KEY.

All tenant tables are protected by RLS — firm_id is set automatically
per request. No WHERE firm_id = ? needed in any query (explicit firm_id
predicates remain harmless and act as defense-in-depth).
"""

import os
import json
import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
from fastapi import Request, Depends
from typing import Generator

# ── connection pool (one global instance) ─────────────────────────────────────

_pool: pg_pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    """Call once at startup in main.py, before app.include_router(...)."""
    global _pool
    if _pool is not None:
        return
    _pool = pg_pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=20,
        dsn=os.environ["DATABASE_URL"],          # set in .env
        cursor_factory=psycopg2.extras.RealDictCursor,   # rows come back as dicts
    )


def _checkout(firm_id: str = "default") -> psycopg2.extensions.connection:
    """
    Check out a connection from the pool and set the RLS tenant context.
    Session-level (is_local=false) so the setting survives commits within
    the checkout. Always call _checkin() when done, or use get_conn().
    """
    if _pool is None:
        raise RuntimeError("Postgres pool not initialised — call init_pool() at startup")
    conn = _pool.getconn()
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_firm_id', %s, false)", (str(firm_id),))
    conn.commit()
    return conn


def _checkin(conn: psycopg2.extensions.connection) -> None:
    try:
        conn.rollback()   # clear any uncommitted state before returning
        # Reset session-level tenant context so the pooled connection cannot
        # leak this request's firm_id into the next checkout.
        with conn.cursor() as cur:
            cur.execute("RESET app.current_firm_id")
        conn.commit()
    except Exception:
        pass
    _pool.putconn(conn)


# ── synchronous helper (for non-async module files) ───────────────────────────

class PgConn:
    """
    Drop-in replacement for the sqlite3 connection pattern used across modules.

    Usage:
        from backend.demo1.pg import get_conn

        with get_conn(firm_id) as conn:
            rows = conn.execute("SELECT * FROM cases")   # firm_id filter via RLS

    Note: __exit__ commits on clean exit, so explicit conn.commit() calls in
    module code are redundant (but harmless).
    """

    def __init__(self, firm_id: str = "default"):
        self._firm_id = firm_id
        self._conn: psycopg2.extensions.connection | None = None

    def __enter__(self):
        self._conn = _checkout(self._firm_id)
        return self

    def __exit__(self, exc_type, *_):
        if self._conn:
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
            _checkin(self._conn)
            self._conn = None

    def execute(self, sql: str, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        """No-op — connection returns to pool on __exit__. Kept for API compat."""
        pass


def get_conn(firm_id: str = "default") -> PgConn:
    """
    Use as a context manager:
        with get_conn(firm_id) as conn:
            rows = conn.execute("SELECT * FROM cases").fetchall()
    """
    return PgConn(firm_id)


# ── FastAPI dependency ─────────────────────────────────────────────────────────

def db_dep(request: Request) -> Generator:
    """
    FastAPI dependency that yields a Postgres connection scoped to the
    request's firm_id (set by TenantMiddleware / force_waw_tenant).

    Usage in a router:
        @router.get("/cases")
        def list_cases(db = Depends(db_dep)):
            return db.execute("SELECT * FROM cases").fetchall()
    """
    firm_id = getattr(request.state, "firm_id", "default")
    conn = _checkout(firm_id)
    pg = PgConn.__new__(PgConn)
    pg._conn = conn
    pg._firm_id = firm_id
    try:
        yield pg
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _checkin(conn)


# ── tenant middleware (add to main.py) ────────────────────────────────────────

def make_tenant_middleware():
    """
    Returns a Starlette middleware class. Reads the JWT Authorization header
    and writes firm_id to request.state so db_dep (above) can pick it up.

    In ACP-VCF single-tenant mode, force_waw_tenant in main.py runs closer to
    the route and overwrites firm_id with FIRM_ID — this middleware then only
    matters if multi-tenant mode ever returns.
    """
    import jwt as pyjwt
    from starlette.middleware.base import BaseHTTPMiddleware

    # Unified with main.py/auth.py: JWT_SECRET_KEY first, legacy SECRET_KEY fallback.
    SECRET = os.environ.get("JWT_SECRET_KEY") or os.environ.get("SECRET_KEY", "change_me")

    class TenantMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            firm_id = "default"
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                try:
                    payload = pyjwt.decode(
                        auth[7:], SECRET, algorithms=["HS256"]
                    )
                    firm_id = payload.get("firm_id") or "default"
                except Exception:
                    pass
            request.state.firm_id = firm_id
            return await call_next(request)

    return TenantMiddleware


# ── utility: row helpers ───────────────────────────────────────────────────────

def row_to_dict(row) -> dict:
    """RealDictCursor rows are already dicts — this is a no-op kept for compat."""
    if row is None:
        return {}
    return dict(row)


def rows_to_list(rows) -> list:
    return [dict(r) for r in rows]


def json_col(val) -> str | None:
    """Serialize a Python object to JSON string for storage."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return json.dumps(val)


def parse_json_col(val):
    """Deserialize a JSON string from Postgres."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (ValueError, TypeError):
        return val
