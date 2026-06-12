"""
morning_brief_router.py — Daily Morning Brief
=============================================
Generates one daily brief per firm at 8am.
Composes: deadlines, approval queue, matter changes,
risk watcher last assessment, unread high-priority notifications.

Mount in main.py:
    from backend.demo1.routers.morning_brief_router import router as brief_router, generate_morning_brief
    app.include_router(brief_router, prefix="/brief", tags=["brief"])
"""

import json, logging
from datetime import datetime, timezone, timedelta, date
from fastapi import APIRouter, Depends, HTTPException
from backend.demo1.auth import get_current_user, get_current_firm_id
from backend.demo1.pg import get_conn

router = APIRouter()
log    = logging.getLogger(__name__)

FIRMS  = ["default", "firm_abc", "meridian_legal"]


# ── Generator (called by scheduler + manually) ────────────────────────────────

def generate_morning_brief(firm_id: str) -> dict:
    """
    Compose the morning brief for a firm.
    Returns the brief_json dict and summary_text string.
    """
    now      = datetime.now(timezone.utc)
    today    = now.date()
    in_72h   = now + timedelta(hours=72)
    since_24 = now - timedelta(hours=24)

    brief = {
        "generated_at":   now.isoformat(),
        "firm_id":        firm_id,
        "deadlines":      [],
        "approval_queue": [],
        "matter_changes": [],
        "risk_snapshot":  None,
        "urgent_notifications": [],
        "unconfirmed_docketing": [],
    }

    with get_conn("default") as conn:

        # 1. Deadlines in next 72h
        try:
            deadlines = conn.execute("""
                SELECT ce.id, ce.title, ce.due_date, ce.event_type,
                       ce.is_court_date, ce.matter_id,
                       c.case_number, c.client_name
                FROM calendar_events ce
                LEFT JOIN cases c ON c.id = ce.matter_id AND c.firm_id = ce.firm_id
                WHERE ce.firm_id=%s
                  AND ce.due_date BETWEEN %s AND %s
                  AND ce.status != 'completed'
                ORDER BY ce.due_date ASC
                LIMIT 20
            """, (firm_id, today, in_72h.date())).fetchall()

            for d in deadlines:
                d = dict(d)
                days_away = (d["due_date"] - today).days if d.get("due_date") else None
                d["days_away"]  = days_away
                d["urgency"]    = "today" if days_away == 0 else ("tomorrow" if days_away == 1 else f"in {days_away} days")
                d["due_date"]   = d["due_date"].isoformat() if d.get("due_date") else None
                brief["deadlines"].append(d)
        except Exception as e:
            log.warning(f"[MorningBrief] Deadlines error: {e}")

        # 2. Pending approval queue items
        try:
            queue_items = conn.execute("""
                SELECT id, item_type, title, recommended, priority, due_by, created_at
                FROM approval_queue
                WHERE firm_id=%s AND status='pending'
                ORDER BY priority ASC, due_by ASC NULLS LAST
                LIMIT 10
            """, (firm_id,)).fetchall()

            for q in queue_items:
                q = dict(q)
                for f in ["due_by", "created_at"]:
                    if q.get(f) and hasattr(q[f], "isoformat"):
                        q[f] = q[f].isoformat()
                brief["approval_queue"].append(q)
        except Exception as e:
            log.warning(f"[MorningBrief] Approval queue error: {e}")

        # 3. Matters that changed status in last 24h
        try:
            changes = conn.execute("""
                SELECT id, case_number, client_name, status, updated_at
                FROM cases
                WHERE firm_id=%s
                  AND updated_at > %s
                  AND deleted = false
                ORDER BY updated_at DESC
                LIMIT 10
            """, (firm_id, since_24)).fetchall()

            for c in changes:
                c = dict(c)
                if c.get("updated_at") and hasattr(c["updated_at"], "isoformat"):
                    c["updated_at"] = c["updated_at"].isoformat()
                brief["matter_changes"].append(c)
        except Exception as e:
            log.warning(f"[MorningBrief] Matter changes error: {e}")

        # 4. Last risk watcher assessment
        try:
            risk = conn.execute("""
                SELECT risk_level, summary, prediction, assessed_at
                FROM risk_assessments
                ORDER BY id DESC LIMIT 1
            """).fetchone()
            if risk:
                r = dict(risk)
                if r.get("assessed_at") and hasattr(r["assessed_at"], "isoformat"):
                    r["assessed_at"] = r["assessed_at"].isoformat()
                brief["risk_snapshot"] = r
        except Exception as e:
            log.warning(f"[MorningBrief] Risk snapshot error: {e}")

        # 5. Unread high-priority notifications (priority <= 2)
        try:
            notifs = conn.execute("""
                SELECT id, type, title, body, link, created_at
                FROM notifications
                WHERE firm_id=%s AND read=FALSE AND priority <= 2
                ORDER BY priority ASC, created_at DESC
                LIMIT 10
            """, (firm_id,)).fetchall()

            for n in notifs:
                n = dict(n)
                if n.get("created_at") and hasattr(n["created_at"], "isoformat"):
                    n["created_at"] = n["created_at"].isoformat()
                brief["urgent_notifications"].append(n)
        except Exception as e:
            log.warning(f"[MorningBrief] Notifications error: {e}")

        # 6. Unconfirmed docketing events
        try:
            dock_items = conn.execute("""
                SELECT de.id, de.title, de.calculated_date, de.jurisdiction,
                       de.rule_reference, de.event_type, de.matter_id,
                       EXTRACT(DAY FROM NOW() - de.created_at)::INTEGER AS days_unconfirmed,
                       c.case_number, c.client_name
                FROM docketing_events de
                JOIN cases c ON c.id = de.matter_id
                WHERE de.firm_id=%s AND de.confirmation_state='pending'
                ORDER BY de.calculated_date ASC
                LIMIT 10
            """, (firm_id,)).fetchall()
            for d in dock_items:
                d = dict(d)
                if d.get("calculated_date") and hasattr(d["calculated_date"], "isoformat"):
                    d["calculated_date"] = d["calculated_date"].isoformat()
                brief["unconfirmed_docketing"].append(d)
        except Exception as e:
            log.warning(f"[MorningBrief] Docketing events error: {e}")

    # Build plain-text summary for voice/email
    lines = [f"Good morning. Here is your ParaIQ brief for {today.strftime('%A, %B %d')}."]

    if brief["deadlines"]:
        lines.append(f"\n{len(brief['deadlines'])} deadline{'s' if len(brief['deadlines']) != 1 else ''} in the next 72 hours:")
        for d in brief["deadlines"][:5]:
            lines.append(f"  - {d['title']} — {d['urgency']}{'  (COURT DATE)' if d.get('is_court_date') else ''}")

    if brief["approval_queue"]:
        lines.append(f"\n{len(brief['approval_queue'])} item{'s' if len(brief['approval_queue']) != 1 else ''} awaiting your approval:")
        for q in brief["approval_queue"][:5]:
            lines.append(f"  - {q['title']}")

    if brief["matter_changes"]:
        lines.append(f"\n{len(brief['matter_changes'])} matter{'s' if len(brief['matter_changes']) != 1 else ''} updated overnight:")
        for c in brief["matter_changes"][:3]:
            lines.append(f"  - {c['client_name']} ({c['case_number']}) — now {c['status']}")

    if brief["unconfirmed_docketing"]:
        lines.append(f"\n⚠ {len(brief['unconfirmed_docketing'])} docketing deadline{'s' if len(brief['unconfirmed_docketing']) != 1 else ''} awaiting attorney confirmation:")
        for d in brief["unconfirmed_docketing"][:5]:
            days = d.get("days_unconfirmed") or 0
            lap = f" — {days}d unconfirmed" if days > 0 else ""
            lines.append(f"  - {d['title']} ({d['jurisdiction']}) · {d['calculated_date']}{lap}")
            lines.append(f"    Confirm at: https://app.para-iq.com/matters/{d.get('matter_id', '')}")

    if brief["risk_snapshot"]:
        r = brief["risk_snapshot"]
        lines.append(f"\nSystem status: {r['risk_level'].upper()} — {r['summary']}")

    if not brief["deadlines"] and not brief["approval_queue"] and not brief["unconfirmed_docketing"]:
        lines.append("\nNo urgent items today. Clear schedule.")

    summary_text = "\n".join(lines)

    # Save to DB (upsert by firm+date)
    try:
        with get_conn("default") as conn:
            conn.execute("""
                INSERT INTO morning_briefs (firm_id, brief_date, brief_json, summary_text, delivered)
                VALUES (%s, %s, %s, %s, false)
                ON CONFLICT (firm_id, brief_date)
                DO UPDATE SET brief_json=%s, summary_text=%s, generated_at=NOW(), delivered=false
            """, (
                firm_id, today,
                json.dumps(brief), summary_text,
                json.dumps(brief), summary_text,
            ))
    except Exception as e:
        log.error(f"[MorningBrief] Save failed: {e}")

    log.info(f"[MorningBrief] Generated for {firm_id}: {len(brief['deadlines'])} deadlines, {len(brief['approval_queue'])} approvals, {len(brief['unconfirmed_docketing'])} unconfirmed docketing")
    return {"brief": brief, "summary_text": summary_text}


def run_all_firms_brief():
    """Called by scheduler at 8am daily."""
    for firm_id in FIRMS:
        try:
            generate_morning_brief(firm_id)
        except Exception as e:
            log.error(f"[MorningBrief] Failed for {firm_id}: {e}")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/today")
def get_today_brief(
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """Get today's brief — generate on demand if not yet created."""
    today = date.today()
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT * FROM morning_briefs WHERE firm_id=%s AND brief_date=%s",
            (firm_id, today)
        ).fetchone()

    if not row:
        # Generate on demand if scheduler hasn't run yet
        result = generate_morning_brief(firm_id)
        return result

    d = dict(row)
    if d.get("generated_at") and hasattr(d["generated_at"], "isoformat"):
        d["generated_at"] = d["generated_at"].isoformat()
    if isinstance(d.get("brief_json"), str):
        d["brief_json"] = json.loads(d["brief_json"])
    return {"brief": d["brief_json"], "summary_text": d["summary_text"]}


@router.get("/today/voice")
def get_today_brief_voice(
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """Plain text summary optimized for TTS voice playback."""
    today = date.today()
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT summary_text FROM morning_briefs WHERE firm_id=%s AND brief_date=%s",
            (firm_id, today)
        ).fetchone()

    if not row:
        result = generate_morning_brief(firm_id)
        return {"summary_text": result["summary_text"]}

    return {"summary_text": row["summary_text"]}


@router.post("/generate")
def force_generate(
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """Force regenerate today's brief (super admin or attorney)."""
    if user.get("role") not in ("paraiq_super", "admin", "attorney"):
        raise HTTPException(403, "Insufficient permissions")
    result = generate_morning_brief(firm_id)
    return {"ok": True, "summary_text": result["summary_text"]}


@router.get("/history")
def brief_history(
    limit:   int = 7,
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """Last N days of briefs for the firm."""
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT id, brief_date, generated_at, summary_text, delivered
            FROM morning_briefs
            WHERE firm_id=%s
            ORDER BY brief_date DESC
            LIMIT %s
        """, (firm_id, limit)).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        for f in ["brief_date", "generated_at"]:
            if d.get(f) and hasattr(d[f], "isoformat"):
                d[f] = d[f].isoformat()
        items.append(d)
    return {"items": items}
