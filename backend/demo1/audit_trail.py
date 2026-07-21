"""
audit_trail.py
==============
FastAPI Middleware + APIRouter: Audit Trail (#20)
Logs every API request to the audit_log table in Supabase Postgres.
"""

import asyncio
import time
import csv as _csv
import io as _io
import logging
import jwt
import psycopg2
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse as SR
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_auth(request: Request):
    """Raise 401 if no valid JWT was decoded by TenantMiddleware."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")


# ── DB Setup ───────────────────────────────────────────────────────────────────

def init_audit_table():
    """No-op — table exists in Supabase Postgres."""
    print("[AuditTrail] Table initialized ✓")


def log_request(method, endpoint, status_code, response_time_ms,
                client_ip, body_size, error=None, user_id=None, firm_id="default"):
    try:
        with get_conn(firm_id) as conn:
            conn.execute("""
                INSERT INTO audit_log
                  (timestamp, method, endpoint, status_code,
                   response_time_ms, client_ip, body_size_bytes, error, user_id, firm_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                datetime.now(timezone.utc).isoformat(),
                method, endpoint, status_code,
                round(response_time_ms, 2),
                client_ip, body_size,
                str(error) if error else None,
                user_id,
                firm_id,
            ))
    except (psycopg2.Error, OSError, ValueError) as e:
        logger.error(f"[AuditTrail] Log error: {e}")


# ── Middleware ─────────────────────────────────────────────────────────────────

class AuditMiddleware(BaseHTTPMiddleware):
    """Intercepts every request and logs it to audit_log."""

    SKIP_PATHS    = {"/docs", "/openapi.json", "/redoc", "/favicon.ico", "/health"}
    SKIP_PREFIXES = ("/export/",)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in self.SKIP_PATHS or any(path.startswith(p) for p in self.SKIP_PREFIXES):
            return await call_next(request)

        start     = time.perf_counter()
        client_ip = request.client.host if request.client else "unknown"

        # Extract user_id + firm_id from JWT if present
        user_id = None
        firm_id = "default"
        auth_hdr = request.headers.get("authorization", "")
        if auth_hdr.startswith("Bearer "):
            try:
                import jwt as _jwt
                import os as _os
                _payload = _jwt.decode(
                    auth_hdr[7:],
                    _os.environ.get("JWT_SECRET_KEY", ""),
                    algorithms=["HS256"],
                    options={"verify_exp": True},
                )
                user_id = int(_payload["sub"]) if _payload.get("sub") else None
                firm_id = _payload.get("firm_id", "default")
            except jwt.ExpiredSignatureError:
                logger.debug("[AuditTrail] Expired JWT in audit middleware")
            except jwt.InvalidTokenError as e:
                logger.debug(f"[AuditTrail] Invalid JWT in audit middleware: {e}")
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"[AuditTrail] JWT decode failed in middleware: {e}")

        body      = await request.body()
        body_size = len(body)

        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive

        status_code = 500
        error       = None
        try:
            response    = await call_next(request)
            status_code = response.status_code
        except (RuntimeError, OSError, asyncio.CancelledError) as e:
            logger.error(f"[AuditTrail] Unhandled error in {request.method} {path}: {e}")
            error    = "internal server error"
            response = JSONResponse({"detail": "Internal server error"}, status_code=500)

        elapsed_ms = (time.perf_counter() - start) * 1000

        log_request(
            method           = request.method,
            endpoint         = path,
            status_code      = status_code,
            response_time_ms = elapsed_ms,
            client_ip        = client_ip,
            body_size        = body_size,
            error            = error,
            user_id          = user_id,
            firm_id          = firm_id,
        )

        return response


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/logs")
def get_audit_logs(
    request:  Request,
    endpoint: Optional[str] = None,
    method:   Optional[str] = None,
    status:   Optional[int] = None,
    limit:    int           = 50,
):
    _require_auth(request)
    limit   = min(limit, 200)
    firm_id = getattr(request.state, "firm_id", "default")
    sql     = "SELECT * FROM audit_log WHERE firm_id = %s"
    params  = [firm_id]

    if endpoint:
        sql += " AND endpoint ILIKE %s"
        params.append(f"%{endpoint}%")
    if method:
        sql += " AND method = %s"
        params.append(method.upper())
    if status:
        sql += " AND status_code = %s"
        params.append(status)

    sql += " ORDER BY id DESC LIMIT %s"
    params.append(limit)

    with get_conn(firm_id) as conn:
        rows = conn.execute(sql, params).fetchall()

    return {"success": True, "count": len(rows), "logs": [dict(r) for r in rows]}


@router.get("/stats")
def audit_stats(request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE firm_id = %s", (firm_id,)
        ).fetchone()["n"]

        by_endpoint = conn.execute("""
            SELECT endpoint, COUNT(*) AS cnt,
                   ROUND(AVG(response_time_ms)::numeric, 2) AS avg_ms,
                   MIN(status_code) AS min_status,
                   MAX(status_code) AS max_status
            FROM audit_log
            WHERE firm_id = %s
            GROUP BY endpoint
            ORDER BY cnt DESC
            LIMIT 20
        """, (firm_id,)).fetchall()

        by_status = conn.execute("""
            SELECT status_code, COUNT(*) AS cnt
            FROM audit_log
            WHERE firm_id = %s
            GROUP BY status_code
            ORDER BY cnt DESC
        """, (firm_id,)).fetchall()

        slowest = conn.execute("""
            SELECT endpoint, method, response_time_ms, timestamp
            FROM audit_log
            WHERE firm_id = %s
            ORDER BY response_time_ms DESC
            LIMIT 5
        """, (firm_id,)).fetchall()

        errors = conn.execute("""
            SELECT endpoint, method, error, timestamp
            FROM audit_log
            WHERE firm_id = %s AND error IS NOT NULL
            ORDER BY id DESC
            LIMIT 10
        """, (firm_id,)).fetchall()

    return {
        "success":           True,
        "total_requests":    total,
        "by_endpoint":       [dict(r) for r in by_endpoint],
        "by_status_code":    [dict(r) for r in by_status],
        "slowest_endpoints": [dict(r) for r in slowest],
        "recent_errors":     [dict(r) for r in errors],
    }


@router.delete("/logs/clear")
def clear_audit_logs(request: Request):
    """
    Clears audit logs for the caller's firm only (never cross-firm).
    Restricted to paraiq_super. The clear action itself is logged.
    """
    _require_auth(request)
    role = getattr(request.state, "role", "")
    if role != "paraiq_super":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Only super admins may clear audit logs")

    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE firm_id = %s", (firm_id,)
        ).fetchone()["n"]
        conn.execute("DELETE FROM audit_log WHERE firm_id = %s", (firm_id,))

    # Log the clear action itself so there's always a trail
    log_request(
        method           = "DELETE",
        endpoint         = "/audit/logs/clear",
        status_code      = 200,
        response_time_ms = 0,
        client_ip        = request.client.host if request.client else "unknown",
        body_size        = 0,
        error            = None,
        user_id          = getattr(request.state, "user_id", None),
        firm_id          = firm_id,
    )

    return {"success": True, "message": f"Cleared {count} audit log entries for firm '{firm_id}'"}


# ── Chain of Custody (Discovery) ──────────────────────────────────────────────

ACTION_LABELS = {
    ("POST",   "/discovery/intake"):        "Files uploaded to intake queue",
    ("DELETE", "/discovery/queue"):         "File removed from queue",
    ("POST",   "/discovery/process/ocr"):   "OCR processing triggered",
    ("POST",   "/discovery/process/zip"):   "ZIP extraction triggered",
    ("POST",   "/discovery/assign"):        "Files assigned to case",
    ("POST",   "/discovery/extract-dates"): "Date extraction run",
    ("GET",    "/discovery/duplicates"):    "Duplicate scan performed",
    ("POST",   "/bates/configure"):         "Bates production set configured",
    ("POST",   "/bates/stamp"):             "Bates stamping executed",
    ("DELETE", "/bates/log"):               "Bates log cleared",
    ("GET",    "/production/bundle"):       "Production ZIP downloaded",
    ("GET",    "/production/catalog"):      "Production catalog viewed",
}


def label_action(method: str, endpoint: str) -> str:
    for (m, e), label in ACTION_LABELS.items():
        if m == method and endpoint.startswith(e):
            return label
    return f"{method} {endpoint}"


@router.get("/discovery/chain")
def get_chain_of_custody(request: Request, limit: int = 200):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT * FROM audit_log
            WHERE firm_id = %s
              AND (endpoint ILIKE '/discovery/%%'
                OR endpoint ILIKE '/bates/%%'
                OR endpoint ILIKE '/production/%%')
            ORDER BY id ASC
            LIMIT %s
        """, (firm_id, limit)).fetchall()

    entries = []
    for r in rows:
        entries.append({
            "seq":         r["id"],
            "timestamp":   r["timestamp"],
            "action":      label_action(r["method"], r["endpoint"]),
            "method":      r["method"],
            "endpoint":    r["endpoint"],
            "status":      r["status_code"],
            "response_ms": round(r["response_time_ms"] or 0, 1),
            "client_ip":   (r["client_ip"] or "")[:20],
            "ok":          200 <= (r["status_code"] or 0) < 300,
        })

    return {"total": len(entries), "entries": entries}


@router.get("/discovery/chain/export")
def export_chain_csv(request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT * FROM audit_log
            WHERE firm_id = %s
              AND (endpoint ILIKE '/discovery/%%'
                OR endpoint ILIKE '/bates/%%'
                OR endpoint ILIKE '/production/%%')
            ORDER BY id ASC
        """, (firm_id,)).fetchall()

    buf = _io.StringIO()
    w   = _csv.writer(buf)
    w.writerow(["Seq", "Timestamp", "Action", "Method", "Endpoint",
                "Status", "Response ms", "Client IP"])
    for r in rows:
        w.writerow([
            r["id"], r["timestamp"],
            label_action(r["method"], r["endpoint"]),
            r["method"], r["endpoint"],
            r["status_code"], round(r["response_time_ms"] or 0, 1),
            (r["client_ip"] or "")[:20],
        ])

    buf.seek(0)
    return SR(
        _io.BytesIO(buf.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=chain_of_custody.csv"}
    )
