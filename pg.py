"""
backend/demo1/pg.py
===================
Central Postgres module. Drop this into backend/demo1/ and import
get_conn() wherever you currently do sqlite3.connect(DB_PATH).

All tenant tables are protected by RLS — firm_id is set automatically
per request. No WHERE firm_id = ? needed in any query.
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
    Always call _checkin() when done, or use get_conn() context manager.
    """
    if _pool is None:
        raise RuntimeError("Postgres pool not initialised — call init_pool() at startup")
    conn = _pool.getconn()
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_firm_id', %s, true)", (firm_id,))
    conn.commit()
    return conn


def _checkin(conn: psycopg2.extensions.connection) -> None:
    try:
        conn.rollback()   # clear any uncommitted state before returning
    except Exception:
        pass
    _pool.putconn(conn)


# ── synchronous helper (for non-async module files) ───────────────────────────

class PgConn:
    """
    Drop-in replacement for the sqlite3 connection pattern used across modules.

    Usage:
        from backend.demo1.pg import get_conn

        # BEFORE (sqlite3):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM cases WHERE firm_id=?", (fid,)).fetchall()
        conn.close()

        # AFTER (Postgres + RLS):
        with get_conn(firm_id) as conn:
            rows = conn.execute("SELECT * FROM cases")   # firm_id filter via RLS
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
    request's firm_id (set by TenantMiddleware below).

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
    Returns a Starlette middleware class. Add to main.py:

        from backend.demo1.pg import make_tenant_middleware
        app.add_middleware(make_tenant_middleware())

    Reads the JWT Authorization header and writes firm_id to request.state
    so db_dep (above) can pick it up per-request.
    """
    import jwt as pyjwt
    from starlette.middleware.base import BaseHTTPMiddleware

    SECRET = os.environ.get("SECRET_KEY", "change_me")

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
