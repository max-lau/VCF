"""
time_router.py — Passive Time Capture & Certification
======================================================
Silently records attorney activity via 30s heartbeats.
Aggregates into sessions (gap > 5min = new session, min 2min).
Attorney reviews and certifies sessions into billable time entries.

Mount in main.py:
    from backend.demo1.routers.time_router import router as time_router
    app.include_router(time_router, prefix="/time", tags=["time"])
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.demo1.auth import get_current_user, get_current_firm_id
from backend.demo1.pg import get_conn

router = APIRouter()
log    = logging.getLogger(__name__)

MIN_SESSION_MINS = 2      # discard sessions shorter than this
GAP_MINS         = 5      # gap between heartbeats that starts a new session

ACTIVITY_TYPES = ["viewing","drafting","reviewing","research","correspondence","other"]


# ── Pydantic Models ───────────────────────────────────────────────────────

class HeartbeatBody(BaseModel):
    matter_id:     int
    activity_type: str = "viewing"

class SessionUpdate(BaseModel):
    activity_type:  Optional[str] = None
    remarks:        Optional[str] = None
    duration_mins:  Optional[float] = None
    description:    Optional[str] = None

class CertifyBody(BaseModel):
    session_ids:  list[int]
    description:  Optional[str] = None

class BillingRateBody(BaseModel):
    user_id:       int
    username:      str
    role_type:     str
    hourly_rate:   float
    currency:      str = "USD"
    effective_from: Optional[str] = None
    effective_to:   Optional[str] = None
    notes:          Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_rate(conn, user_id: int, firm_id: str) -> Optional[float]:
    """Get the current hourly rate for a user."""
    row = conn.execute("""
        SELECT hourly_rate FROM billing_rates
        WHERE user_id=%s AND firm_id=%s
          AND effective_from <= CURRENT_DATE
          AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
        ORDER BY effective_from DESC LIMIT 1
    """, (user_id, firm_id)).fetchone()
    return float(row["hourly_rate"]) if row else None

def _aggregate_sessions(firm_id: str, user_id: int, matter_id: int):
    """
    Pull recent unclustered heartbeats and group into sessions.
    Sessions with gap > GAP_MINS start a new session.
    Sessions < MIN_SESSION_MINS are discarded.
    """
    with get_conn(firm_id) as conn:
        # Get heartbeats not yet in a session (last 24h)
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        beats = conn.execute("""
            SELECT id, ts, activity_type FROM time_heartbeats
            WHERE firm_id=%s AND user_id=%s AND matter_id=%s AND ts > %s
            ORDER BY ts ASC
        """, (firm_id, user_id, matter_id, since)).fetchall()

        if not beats:
            return

        # Get username
        user_row = conn.execute(
            "SELECT username FROM users WHERE id=%s", (user_id,)
        ).fetchone()
        username = user_row["username"] if user_row else str(user_id)

        # Get billing rate
        rate = _get_rate(conn, user_id, firm_id)

        # Group into sessions
        sessions = []
        current = [beats[0]]
        for beat in beats[1:]:
            gap = (beat["ts"] - current[-1]["ts"]).total_seconds() / 60
            if gap > GAP_MINS:
                sessions.append(current)
                current = [beat]
            else:
                current.append(beat)
        sessions.append(current)

        for session in sessions:
            start = session[0]["ts"]
            end   = session[-1]["ts"]
            # Add one heartbeat interval to end time
            end   = end + timedelta(seconds=30)
            dur   = (end - start).total_seconds() / 60

            if dur < MIN_SESSION_MINS:
                continue

            # Most common activity type in session
            types = [b["activity_type"] for b in session]
            activity = max(set(types), key=types.count)

            billable_amount = None
            if rate:
                billable_amount = round((dur / 60) * rate, 2)

            # Check if session already exists (avoid duplicates)
            exists = conn.execute("""
                SELECT id FROM time_sessions
                WHERE firm_id=%s AND user_id=%s AND matter_id=%s
                  AND started_at=%s
            """, (firm_id, user_id, matter_id, start)).fetchone()

            if not exists:
                conn.execute("""
                    INSERT INTO time_sessions
                        (firm_id, user_id, username, matter_id, activity_type,
                         started_at, ended_at, duration_mins, billable_mins,
                         hourly_rate, billable_amount)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    firm_id, user_id, username, matter_id, activity,
                    start, end, round(dur, 2), round(dur, 2),
                    rate, billable_amount
                ))

        log.info(f"[Time] Aggregated {len(sessions)} sessions for user {user_id} matter {matter_id}")


# ── Routes ────────────────────────────────────────────────────────────────

@router.post("/heartbeat")
def heartbeat(
    body:    HeartbeatBody,
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """30s ping from frontend while matter is open."""
    if body.activity_type not in ACTIVITY_TYPES:
        body.activity_type = "viewing"

    with get_conn(firm_id) as conn:
        conn.execute("""
            INSERT INTO time_heartbeats (firm_id, user_id, matter_id, activity_type)
            VALUES (%s,%s,%s,%s)
        """, (firm_id, user["id"], body.matter_id, body.activity_type))

    # Aggregate sessions every 10th heartbeat (~5 min)
    try:
        with get_conn(firm_id) as conn:
            count = conn.execute("""
                SELECT COUNT(*) AS n FROM time_heartbeats
                WHERE firm_id=%s AND user_id=%s AND matter_id=%s
                  AND ts > NOW() - INTERVAL '1 hour'
            """, (firm_id, user["id"], body.matter_id)).fetchone()["n"]
        if count % 10 == 0:
            _aggregate_sessions(firm_id, user["id"], body.matter_id)
    except Exception as e:
        log.warning(f"[Time] Aggregation error: {e}")

    return {"ok": True}


@router.post("/flush/{matter_id}")
def flush_sessions(
    matter_id: int,
    firm_id:   str = Depends(get_current_firm_id),
    user       = Depends(get_current_user),
):
    """Force aggregate sessions — called when attorney leaves a matter page."""
    try:
        _aggregate_sessions(firm_id, user["id"], matter_id)
    except Exception as e:
        log.warning(f"[Time] Flush error: {e}")
    return {"ok": True}


@router.get("/sessions/pending")
def get_pending_sessions(
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """All uncertified sessions for the current user."""
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT ts.*, c.case_number, c.client_name
            FROM time_sessions ts
            LEFT JOIN cases c ON c.id = ts.matter_id
            WHERE ts.firm_id=%s AND ts.user_id=%s
              AND ts.certified=FALSE AND ts.discarded=FALSE
            ORDER BY ts.started_at DESC
        """, (firm_id, user["id"])).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        for f in ["started_at","ended_at","certified_at","created_at"]:
            if d.get(f) and hasattr(d[f],"isoformat"):
                d[f] = d[f].isoformat()
        items.append(d)
    return {"sessions": items, "count": len(items)}


@router.patch("/sessions/{session_id}")
def update_session(
    session_id: int,
    body:       SessionUpdate,
    firm_id:    str = Depends(get_current_firm_id),
    user        = Depends(get_current_user),
):
    """Attorney edits activity type, remarks, or duration before certifying."""
    with get_conn(firm_id) as conn:
        sess = conn.execute(
            "SELECT * FROM time_sessions WHERE id=%s AND firm_id=%s AND user_id=%s",
            (session_id, firm_id, user["id"])
        ).fetchone()
        if not sess:
            raise HTTPException(404, "Session not found")
        if sess["certified"]:
            raise HTTPException(400, "Cannot edit a certified session")

        updates = {}
        if body.activity_type:
            updates["activity_type"] = body.activity_type
        if body.remarks is not None:
            updates["remarks"] = body.remarks
        if body.duration_mins is not None:
            updates["duration_mins"] = body.duration_mins
            updates["billable_mins"] = body.duration_mins
            rate = sess["hourly_rate"]
            if rate:
                updates["billable_amount"] = round((body.duration_mins / 60) * float(rate), 2)

        if not updates:
            return {"ok": True, "changed": False}

        set_clause = ", ".join(f"{k}=%s" for k in updates)
        conn.execute(
            f"UPDATE time_sessions SET {set_clause} WHERE id=%s",
            list(updates.values()) + [session_id]
        )
    return {"ok": True, "changed": True}


@router.post("/sessions/{session_id}/discard")
def discard_session(
    session_id: int,
    firm_id:    str = Depends(get_current_firm_id),
    user        = Depends(get_current_user),
):
    """Discard a session — won't appear for certification."""
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE time_sessions SET discarded=TRUE WHERE id=%s AND firm_id=%s AND user_id=%s",
            (session_id, firm_id, user["id"])
        )
    return {"ok": True}


@router.post("/certify")
def certify_sessions(
    body:    CertifyBody,
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """Certify one or more sessions — creates time_entries records."""
    if not body.session_ids:
        raise HTTPException(400, "No session IDs provided")

    certified = []
    with get_conn(firm_id) as conn:
        for sid in body.session_ids:
            sess = conn.execute("""
                SELECT ts.*, c.case_number, c.client_name
                FROM time_sessions ts
                LEFT JOIN cases c ON c.id = ts.matter_id
                WHERE ts.id=%s AND ts.firm_id=%s AND ts.user_id=%s
                  AND ts.certified=FALSE AND ts.discarded=FALSE
            """, (sid, firm_id, user["id"])).fetchone()

            if not sess:
                continue
            sess = dict(sess)

            rate = sess.get("hourly_rate") or _get_rate(conn, user["id"], firm_id) or 0
            dur  = float(sess["billable_mins"] or sess["duration_mins"])
            amt  = round((dur / 60) * float(rate), 2)

            # Create time entry
            conn.execute("""
                INSERT INTO time_entries
                    (firm_id, user_id, username, matter_id, session_id,
                     activity_type, remarks, date, duration_mins,
                     hourly_rate, billable_amount, currency, description,
                     certified_by, certified_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'USD',%s,%s,NOW())
            """, (
                firm_id, user["id"], sess.get("username"), sess["matter_id"], sid,
                sess["activity_type"], sess.get("remarks"),
                sess["started_at"].date() if hasattr(sess["started_at"],"date") else sess["started_at"],
                dur, rate, amt,
                body.description or f"Time on {sess.get('client_name','matter')} — {sess['activity_type']}",
                user["id"]
            ))

            # Mark session certified
            conn.execute(
                "UPDATE time_sessions SET certified=TRUE, certified_by=%s, certified_at=NOW() WHERE id=%s",
                (user["id"], sid)
            )
            certified.append(sid)

    return {"ok": True, "certified": len(certified), "session_ids": certified}


@router.get("/entries")
def get_time_entries(
    matter_id: Optional[int] = None,
    firm_id:   str = Depends(get_current_firm_id),
    user       = Depends(get_current_user),
):
    """Time ledger — certified entries for the firm."""
    with get_conn(firm_id) as conn:
        if matter_id:
            rows = conn.execute("""
                SELECT te.*, c.case_number, c.client_name
                FROM time_entries te
                LEFT JOIN cases c ON c.id = te.matter_id
                WHERE te.firm_id=%s AND te.matter_id=%s
                ORDER BY te.date DESC, te.created_at DESC
            """, (firm_id, matter_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT te.*, c.case_number, c.client_name
                FROM time_entries te
                LEFT JOIN cases c ON c.id = te.matter_id
                WHERE te.firm_id=%s AND te.user_id=%s
                ORDER BY te.date DESC, te.created_at DESC
                LIMIT 100
            """, (firm_id, user["id"])).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        for f in ["date","certified_at","created_at"]:
            if d.get(f) and hasattr(d[f],"isoformat"):
                d[f] = d[f].isoformat()
        for f in ["duration_mins","hourly_rate","billable_amount"]:
            if d.get(f) is not None:
                d[f] = float(d[f])
        items.append(d)
    return {"entries": items, "count": len(items)}


@router.get("/summary")
def get_time_summary(
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """Summary stats for the current user."""
    with get_conn(firm_id) as conn:
        pending = conn.execute("""
            SELECT COUNT(*) AS n, COALESCE(SUM(duration_mins),0) AS total_mins
            FROM time_sessions
            WHERE firm_id=%s AND user_id=%s AND certified=FALSE AND discarded=FALSE
        """, (firm_id, user["id"])).fetchone()

        certified = conn.execute("""
            SELECT COUNT(*) AS n, COALESCE(SUM(billable_amount),0) AS total_amount,
                   COALESCE(SUM(duration_mins),0) AS total_mins
            FROM time_entries
            WHERE firm_id=%s AND user_id=%s
        """, (firm_id, user["id"])).fetchone()

        rate = _get_rate(conn, user["id"], firm_id)

    return {
        "pending_sessions":       int(pending["n"]),
        "pending_mins":           float(pending["total_mins"]),
        "certified_entries":      int(certified["n"]),
        "certified_total_amount": float(certified["total_amount"]),
        "certified_total_mins":   float(certified["total_mins"]),
        "hourly_rate":            rate,
    }


# ── Billing Rates (firm admin) ────────────────────────────────────────────

@router.get("/rates")
def get_rates(
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """List all billing rates for the firm."""
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT * FROM billing_rates WHERE firm_id=%s
            ORDER BY username, effective_from DESC
        """, (firm_id,)).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        for f in ["effective_from","effective_to","created_at","updated_at"]:
            if d.get(f) and hasattr(d[f],"isoformat"):
                d[f] = d[f].isoformat()
        for f in ["hourly_rate"]:
            if d.get(f) is not None:
                d[f] = float(d[f])
        items.append(d)
    return {"rates": items}


@router.post("/rates")
def set_rate(
    body:    BillingRateBody,
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """Set or update a billing rate for a user."""
    if user.get("role") not in ("paraiq_super","admin","attorney"):
        raise HTTPException(403, "Insufficient permissions")

    with get_conn(firm_id) as conn:
        conn.execute("""
            INSERT INTO billing_rates
                (firm_id, user_id, username, role_type, hourly_rate,
                 currency, effective_from, effective_to, notes, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            firm_id, body.user_id, body.username, body.role_type,
            body.hourly_rate, body.currency,
            body.effective_from or "today",
            body.effective_to, body.notes, user["id"]
        ))
    return {"ok": True}
