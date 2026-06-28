"""
time_tracker.py — Time Tracking Quick-Log Backend
==================================================
One-click time entry from any action (document review, analysis, drafting,
research, email, call, meeting, filing, discovery, other), plus a dashboard
summary, recent entries list, approval workflow, and CSV export.

This module is a companion to routers/time_router.py (passive heartbeat capture
+ session certification). It writes directly to the same `time_entries` table
but adds a quick-log flow for explicit, action-driven billable entries that
are not tied to a heartbeat session.

Mount in main.py:
    from backend.demo1.time_tracker import router as time_tracker_router
    app.include_router(time_tracker_router, prefix="/time", tags=["time-tracker"])

NOTE: If routers/time_router.py is also mounted at prefix="/time", either
(a) mount this router under a different prefix (e.g. "/time-tracker"), or
(b) use only one of the two /summary endpoints. The quick-log, recent,
approve, and export endpoints here do not collide with time_router.py.
"""

import csv
import io
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from backend.demo1.auth import get_current_user, get_current_firm_id
from backend.demo1.pg import get_conn


router = APIRouter()
log = logging.getLogger(__name__)


# Activity types accepted by the quick-log endpoint. Anything outside this
# set is normalised to "other" so callers can pass arbitrary action names
# (e.g. from a frontend button) without a 400.
ACTIVITY_TYPES = {
    "document_review",
    "analysis",
    "drafting",
    "research",
    "email",
    "call",
    "meeting",
    "filing",
    "discovery",
    "other",
}

# Default minimum billable increment (1/10th of an hour = 6 minutes).
DEFAULT_HOURS = 0.1


# ── Pydantic Models ──────────────────────────────────────────────────────────


class QuickLogBody(BaseModel):
    """One-click time entry payload. `case_id` is the cases.id (== matter_id
    on time_entries). `hours` defaults to 0.1 (6 minutes)."""

    case_id: int
    activity_type: str = "other"
    description: str = ""
    hours: float = Field(default=DEFAULT_HOURS, gt=0, le=24)
    document_id: Optional[int] = None


class ApproveBody(BaseModel):
    """Optional note for the approval action."""

    note: Optional[str] = None


# ── Schema bootstrap ─────────────────────────────────────────────────────────


def _ensure_columns(conn) -> None:
    """Add columns used by this module to the existing time_entries table if
    they are missing. Uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS so it is
    idempotent and safe to call on every request (cheap, no-op after first).

    Columns added:
      - document_id  INT       — link to case_documents.id (optional)
      - approved      BOOLEAN  — billing approval flag (default FALSE)
      - approved_at   TIMESTAMPTZ
      - approved_by   INT       — users.id of approver
      - approved_note TEXT
      - source        TEXT      — 'quick_log' | 'certified' | ...
    """
    stmts = [
        "ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS document_id INT",
        "ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS approved BOOLEAN DEFAULT FALSE",
        "ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ",
        "ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS approved_by INT",
        "ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS approved_note TEXT",
        "ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS source TEXT",
    ]
    cur = conn.cursor()
    for s in stmts:
        try:
            cur.execute(s)
        except Exception as e:  # pragma: no cover — defensive
            log.warning(f"[time_tracker] schema tweak failed ({s}): {e}")
            conn.rollback()
            return
    conn.commit()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_user_rate(conn, user_id: int, firm_id: str) -> Optional[float]:
    """Look up the current effective hourly rate for a user from the
    billing_rates table (same logic as time_router._get_rate). Returns None
    if no rate is configured."""
    try:
        row = conn.execute(
            """
            SELECT hourly_rate FROM billing_rates
            WHERE user_id=%s AND firm_id=%s
              AND effective_from <= CURRENT_DATE
              AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
            ORDER BY effective_from DESC LIMIT 1
            """,
            (user_id, firm_id),
        ).fetchone()
    except Exception as e:
        log.warning(f"[time_tracker] billing rate lookup failed: {e}")
        return None
    return float(row["hourly_rate"]) if row else None


def _get_case_rate(conn, case_id: int, firm_id: str) -> Optional[float]:
    """Look up an hourly rate stored on the case/matter itself. Tries common
    column names defensively. Returns None if not present."""
    candidates = [
        ("cases", "hourly_rate"),
        ("cases", "billing_rate"),
        ("cases", "rate"),
    ]
    for table, col in candidates:
        try:
            exists = conn.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name=%s AND column_name=%s
                """,
                (table, col),
            ).fetchone()
            if not exists:
                continue
            row = conn.execute(
                f"SELECT {col} AS r FROM cases WHERE id=%s AND firm_id=%s",
                (case_id, firm_id),
            ).fetchone()
            if row and row["r"] is not None:
                return float(row["r"])
        except Exception as e:
            log.debug(f"[time_tracker] case rate probe {table}.{col} failed: {e}")
            continue
    return None


def _get_firm_default_rate(conn, firm_id: str) -> Optional[float]:
    """Look up a firm-wide default hourly rate from common settings tables."""
    probes = [
        ("firm_settings", "default_hourly_rate"),
        ("firm_settings", "hourly_rate"),
        ("firm_email_settings", "default_hourly_rate"),
    ]
    for table, col in probes:
        try:
            exists = conn.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name=%s AND column_name=%s
                """,
                (table, col),
            ).fetchone()
            if not exists:
                continue
            row = conn.execute(
                f"SELECT {col} AS r FROM {table} WHERE firm_id=%s LIMIT 1",
                (firm_id,),
            ).fetchone()
            if row and row["r"] is not None:
                return float(row["r"])
        except Exception:
            continue
    return None


def _resolve_rate(conn, user_id: int, firm_id: str, case_id: int) -> Optional[float]:
    """Resolve a billing rate in priority order: user → case → firm."""
    return (
        _get_user_rate(conn, user_id, firm_id)
        or _get_case_rate(conn, case_id, firm_id)
        or _get_firm_default_rate(conn, firm_id)
    )


def _iso(val) -> Optional[str]:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/quick-log")
def quick_log(
    body: QuickLogBody,
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """One-click time entry from any action.

    Creates a `time_entries` record for the current user on the given case,
    with the current timestamp and firm_id. Hours are converted to minutes
    (duration_mins) since that is the native unit of time_entries.
    Returns the created entry.
    """
    if body.activity_type not in ACTIVITY_TYPES:
        body.activity_type = "other"

    user_id = int(user["id"])
    username = user.get("username") or str(user_id)
    duration_mins = round(body.hours * 60, 2)

    with get_conn(firm_id) as conn:
        _ensure_columns(conn)

        # Verify the case exists and belongs to this firm
        case = conn.execute(
            "SELECT id, case_number, client_name FROM cases WHERE id=%s AND firm_id=%s AND deleted=FALSE",
            (body.case_id, firm_id),
        ).fetchone()
        if not case:
            raise HTTPException(404, f"Case {body.case_id} not found")

        # Resolve billing rate
        rate = _resolve_rate(conn, user_id, firm_id, body.case_id)
        billable_amount = (
            round(body.hours * float(rate), 2) if rate is not None else None
        )

        row = conn.execute(
            """
            INSERT INTO time_entries
                (firm_id, user_id, username, matter_id, document_id,
                 activity_type, description, date, duration_mins,
                 hourly_rate, billable_amount, currency, source,
                 certified_by, certified_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'USD','quick_log',%s,NOW())
            RETURNING *
            """,
            (
                firm_id,
                user_id,
                username,
                body.case_id,
                body.document_id,
                body.activity_type,
                body.description,
                date.today(),
                duration_mins,
                rate,
                billable_amount,
                user_id,
            ),
        ).fetchone()

        if row is None:
            raise HTTPException(500, "Failed to create time entry")
        entry = dict(row)

    # Serialise datetimes for JSON
    for f in ("date", "certified_at", "created_at", "approved_at"):
        if entry.get(f) is not None:
            entry[f] = _iso(entry[f])
    for f in ("duration_mins", "hourly_rate", "billable_amount"):
        if entry.get(f) is not None:
            entry[f] = float(entry[f])

    log.info(
        f"[time_tracker] quick-log user={user_id} case={body.case_id} "
        f"activity={body.activity_type} hours={body.hours}"
    )
    return {"entry": entry}


@router.get("/summary")
def summary(
    days: int = Query(30, ge=1, le=365),
    case_id: Optional[int] = Query(None),
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """Dashboard summary for the firm (optionally scoped to a case).

    Returns total_hours, total_entries, hours_by_activity, hours_by_day,
    and billable_amount for the last `days` days.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    user_id = int(user["id"])

    with get_conn(firm_id) as conn:
        _ensure_columns(conn)

        params = [firm_id, since]
        case_clause = ""
        if case_id is not None:
            case_clause = " AND matter_id=%s"
            params.append(case_id)

        # Aggregate totals
        totals = conn.execute(
            f"""
            SELECT COUNT(*) AS n,
                   COALESCE(SUM(duration_mins),0) AS total_mins,
                   COALESCE(SUM(billable_amount),0) AS total_amount
            FROM time_entries
            WHERE firm_id=%s AND created_at >= %s{case_clause}
            """,
            params,
        ).fetchone()

        # Hours by activity type
        act_rows = conn.execute(
            f"""
            SELECT activity_type,
                   COALESCE(SUM(duration_mins),0) AS mins
            FROM time_entries
            WHERE firm_id=%s AND created_at >= %s{case_clause}
            GROUP BY activity_type
            """,
            params,
        ).fetchall()

        # Hours by day
        day_rows = conn.execute(
            f"""
            SELECT to_char(date, 'YYYY-MM-DD') AS d,
                   COALESCE(SUM(duration_mins),0) AS mins
            FROM time_entries
            WHERE firm_id=%s AND created_at >= %s{case_clause}
            GROUP BY d
            ORDER BY d ASC
            """,
            params,
        ).fetchall()

        # Resolve an average/applicable rate for billable_amount fallback.
        # Use the firm-wide total_amount already computed (entries store their
        # own billable_amount at creation time). If null/zero, compute from a
        # best-effort rate.
        total_amount = float(totals["total_amount"] or 0)
        total_mins = float(totals["total_mins"] or 0)
        total_hours = round(total_mins / 60, 4) if total_mins else 0.0

        if total_amount == 0 and total_hours > 0 and case_id is not None:
            rate = _resolve_rate(conn, user_id, firm_id, case_id)
            if rate:
                total_amount = round(total_hours * float(rate), 2)
        elif total_amount == 0 and total_hours > 0:
            rate = _get_user_rate(conn, user_id, firm_id) or _get_firm_default_rate(
                conn, firm_id
            )
            if rate:
                total_amount = round(total_hours * float(rate), 2)

    hours_by_activity = {
        (r["activity_type"] or "other"): round(float(r["mins"]) / 60, 4)
        for r in act_rows
    }
    hours_by_day = [
        {"date": r["d"], "hours": round(float(r["mins"]) / 60, 4)}
        for r in day_rows
    ]

    return {
        "days": days,
        "case_id": case_id,
        "total_hours": total_hours,
        "total_entries": int(totals["n"] or 0),
        "hours_by_activity": hours_by_activity,
        "hours_by_day": hours_by_day,
        "billable_amount": round(total_amount, 2),
    }


@router.get("/recent")
def recent(
    limit: int = Query(20, ge=1, le=200),
    case_id: Optional[int] = Query(None),
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """Recent time entries for the firm, optionally scoped to a case.

    Returns a list of {case_number, client_name, activity_type, description,
    hours, user_name, logged_at}.
    """
    params = [firm_id]
    case_clause = ""
    if case_id is not None:
        case_clause = " AND te.matter_id=%s"
        params.append(case_id)
    params.append(limit)

    with get_conn(firm_id) as conn:
        _ensure_columns(conn)
        rows = conn.execute(
            f"""
            SELECT te.id, te.activity_type, te.description,
                   te.duration_mins, te.created_at, te.approved,
                   c.case_number, c.client_name,
                   u.username AS user_name
            FROM time_entries te
            LEFT JOIN cases c ON c.id = te.matter_id
            LEFT JOIN users u ON u.id = te.user_id
            WHERE te.firm_id=%s{case_clause}
            ORDER BY te.created_at DESC
            LIMIT %s
            """,
            params,
        ).fetchall()

    items = []
    for r in rows:
        r = dict(r)
        items.append(
            {
                "id": r["id"],
                "case_number": r.get("case_number"),
                "client_name": r.get("client_name"),
                "activity_type": r.get("activity_type"),
                "description": r.get("description"),
                "hours": round(float(r["duration_mins"] or 0) / 60, 4),
                "user_name": r.get("user_name"),
                "logged_at": _iso(r.get("created_at")),
                "approved": bool(r.get("approved")) if r.get("approved") is not None else False,
            }
        )
    return {"entries": items, "count": len(items)}


@router.post("/{entry_id}/approve")
def approve_entry(
    entry_id: int,
    body: ApproveBody = ApproveBody(),
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """Mark a time entry as approved for billing. Requires auth.

    Only firm admins / attorneys / paraiq_super can approve. The entry must
    belong to the caller's firm.
    """
    if user.get("role") not in ("admin", "firm_admin", "paraiq_super", "attorney"):
        raise HTTPException(403, "Insufficient permissions to approve time entries")

    user_id = int(user["id"])

    with get_conn(firm_id) as conn:
        _ensure_columns(conn)
        row = conn.execute(
            "SELECT id, approved FROM time_entries WHERE id=%s AND firm_id=%s",
            (entry_id, firm_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Time entry not found")
        if row.get("approved"):
            return {"ok": True, "already_approved": True, "entry_id": entry_id}

        conn.execute(
            """
            UPDATE time_entries
            SET approved=TRUE, approved_at=NOW(), approved_by=%s, approved_note=%s
            WHERE id=%s AND firm_id=%s
            """,
            (user_id, body.note, entry_id, firm_id),
        )

    log.info(f"[time_tracker] entry {entry_id} approved by user={user_id}")
    return {"ok": True, "entry_id": entry_id, "approved_by": user_id}


@router.get("/export", response_class=PlainTextResponse)
def export_entries(
    case_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """Export time entries as a CSV string.

    Query params:
      - case_id (optional): scope to a single case
      - date_from (optional, YYYY-MM-DD): inclusive lower bound on entry date
      - date_to (optional, YYYY-MM-DD): inclusive upper bound on entry date
    Returns CSV text with columns: id, date, case_number, client_name,
    user_name, activity_type, description, hours, hourly_rate,
    billable_amount, approved.
    """
    clauses = ["te.firm_id=%s"]
    params: list = [firm_id]
    if case_id is not None:
        clauses.append("te.matter_id=%s")
        params.append(case_id)
    if date_from:
        try:
            datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "date_from must be YYYY-MM-DD")
        clauses.append("te.date >= %s")
        params.append(date_from)
    if date_to:
        try:
            datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "date_to must be YYYY-MM-DD")
        clauses.append("te.date <= %s")
        params.append(date_to)

    where = " AND ".join(clauses)

    with get_conn(firm_id) as conn:
        _ensure_columns(conn)
        rows = conn.execute(
            f"""
            SELECT te.id, te.date, te.activity_type, te.description,
                   te.duration_mins, te.hourly_rate, te.billable_amount,
                   te.approved, te.created_at,
                   c.case_number, c.client_name,
                   u.username AS user_name
            FROM time_entries te
            LEFT JOIN cases c ON c.id = te.matter_id
            LEFT JOIN users u ON u.id = te.user_id
            WHERE {where}
            ORDER BY te.date DESC, te.created_at DESC
            """,
            params,
        ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "date",
            "case_number",
            "client_name",
            "user_name",
            "activity_type",
            "description",
            "hours",
            "hourly_rate",
            "billable_amount",
            "approved",
        ]
    )
    for r in rows:
        r = dict(r)
        writer.writerow(
            [
                r["id"],
                _iso(r.get("date")) or "",
                r.get("case_number") or "",
                r.get("client_name") or "",
                r.get("user_name") or "",
                r.get("activity_type") or "",
                (r.get("description") or "").replace("\n", " "),
                round(float(r["duration_mins"] or 0) / 60, 4),
                f"{float(r['hourly_rate']):.2f}" if r.get("hourly_rate") is not None else "",
                f"{float(r['billable_amount']):.2f}" if r.get("billable_amount") is not None else "",
                "yes" if r.get("approved") else "no",
            ]
        )

    filename = f"time_entries_{firm_id}"
    if case_id is not None:
        filename += f"_case{case_id}"
    if date_from or date_to:
        filename += f"_{date_from or 'start'}_to_{date_to or 'now'}"
    filename += ".csv"

    return PlainTextResponse(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
