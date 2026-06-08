"""
audit_trail.py
==============
FastAPI Middleware + APIRouter: Audit Trail (#20)
Logs every API request to the audit_log table in Supabase Postgres.
"""

import time
import csv as _csv
import io as _io
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse as SR
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

from backend.demo1.pg import get_conn

router = APIRouter()


# ── DB Setup ───────────────────────────────────────────────────────────────────

def init_audit_table():
    """No-op — table exists in Supabase Postgres."""
    print("[AuditTrail] Table initialized ✓")


def log_request(method, endpoint, status_code, response_time_ms,
                client_ip, body_size, error=None):
    try:
        with get_conn("default") as conn:
            conn.execute("""
                INSERT INTO audit_log
                  (timestamp, method, endpoint, status_code,
                   response_time_ms, client_ip, body_size_bytes, error)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                datetime.now(timezone.utc).isoformat(),
                method, endpoint, status_code,
                round(response_time_ms, 2),
                client_ip, body_size,
                str(error) if error else None,
            ))
    except Exception as e:
        print(f"[AuditTrail] Log error: {e}")


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
        except Exception as e:
            error    = str(e)
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
        )

        return response


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/logs")
def get_audit_logs(
    endpoint: Optional[str] = None,
    method:   Optional[str] = None,
    status:   Optional[int] = None,
    limit:    int           = 50,
):
    limit  = min(limit, 200)
    sql    = "SELECT * FROM audit_log WHERE TRUE"
    params = []

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

    with get_conn("default") as conn:
        rows = conn.execute(sql, params).fetchall()

    return {"success": True, "count": len(rows), "logs": [dict(r) for r in rows]}


@router.get("/stats")
def audit_stats():
    with get_conn("default") as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log"
        ).fetchone()["n"]

        by_endpoint = conn.execute("""
            SELECT endpoint, COUNT(*) AS cnt,
                   ROUND(AVG(response_time_ms)::numeric, 2) AS avg_ms,
                   MIN(status_code) AS min_status,
                   MAX(status_code) AS max_status
            FROM audit_log
            GROUP BY endpoint
            ORDER BY cnt DESC
            LIMIT 20
        """).fetchall()

        by_status = conn.execute("""
            SELECT status_code, COUNT(*) AS cnt
            FROM audit_log
            GROUP BY status_code
            ORDER BY cnt DESC
        """).fetchall()

        slowest = conn.execute("""
            SELECT endpoint, method, response_time_ms, timestamp
            FROM audit_log
            ORDER BY response_time_ms DESC
            LIMIT 5
        """).fetchall()

        errors = conn.execute("""
            SELECT endpoint, method, error, timestamp
            FROM audit_log
            WHERE error IS NOT NULL
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()

    return {
        "success":           True,
        "total_requests":    total,
        "by_endpoint":       [dict(r) for r in by_endpoint],
        "by_status_code":    [dict(r) for r in by_status],
        "slowest_endpoints": [dict(r) for r in slowest],
        "recent_errors":     [dict(r) for r in errors],
    }


@router.delete("/logs/clear")
def clear_audit_logs():
    with get_conn("default") as conn:
        conn.execute("DELETE FROM audit_log")
    return {"success": True, "message": "Audit log cleared"}


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
def get_chain_of_custody(limit: int = 200):
    with get_conn("default") as conn:
        rows = conn.execute("""
            SELECT * FROM audit_log
            WHERE (endpoint ILIKE '/discovery/%'
                OR endpoint ILIKE '/bates/%'
                OR endpoint ILIKE '/production/%')
            ORDER BY id ASC
            LIMIT %s
        """, (limit,)).fetchall()

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
def export_chain_csv():
    with get_conn("default") as conn:
        rows = conn.execute("""
            SELECT * FROM audit_log
            WHERE (endpoint ILIKE '/discovery/%'
                OR endpoint ILIKE '/bates/%'
                OR endpoint ILIKE '/production/%')
            ORDER BY id ASC
        """).fetchall()

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
