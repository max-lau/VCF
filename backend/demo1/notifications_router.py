"""
notifications_router.py — In-app Notification Center
=====================================================
Mount in main.py:
    from backend.demo1.notifications_router import router as notifications_router
    app.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
"""

import os, logging
import psycopg2
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.demo1.auth import get_current_user, get_current_firm_id
from backend.demo1.pg import get_conn

router = APIRouter()
log    = logging.getLogger(__name__)


# ── List notifications ────────────────────────────────────────────────────────

@router.get("/notifications")
def list_notifications(
    limit:    int = 30,
    unread_only: bool = False,
    firm_id:  str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        query = """
            SELECT id, firm_id, user_id, type, title, body, link, read, created_at
            FROM notifications
            WHERE firm_id=%s
        """
        params = [firm_id]
        if unread_only:
            query += " AND read=FALSE"
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
            items.append(d)

        # Unread count
        unread = conn.execute(
            "SELECT COUNT(*) AS cnt FROM notifications WHERE firm_id=%s AND read=FALSE",
            (firm_id,)
        ).fetchone()["cnt"]

    return {"items": items, "unread": unread}


# ── Mark read ─────────────────────────────────────────────────────────────────

@router.patch("/notifications/{notif_id}/read")
def mark_read(
    notif_id: int,
    firm_id:  str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE notifications SET read=TRUE WHERE id=%s AND firm_id=%s",
            (notif_id, firm_id)
        )
    return {"ok": True}


@router.patch("/notifications/read-all")
def mark_all_read(
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE notifications SET read=TRUE WHERE firm_id=%s AND read=FALSE",
            (firm_id,)
        )
    return {"ok": True}


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/notifications/clear-all")
def clear_all(
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "DELETE FROM notifications WHERE firm_id=%s AND read=TRUE",
            (firm_id,)
        )
    return {"ok": True}

@router.delete("/notifications/{notif_id}")
def delete_notification(
    notif_id: int,
    firm_id:  str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "DELETE FROM notifications WHERE id=%s AND firm_id=%s",
            (notif_id, firm_id)
        )
    return {"ok": True}





# ── Generate notifications (called by scheduler) ──────────────────────────────

def generate_notifications(firm_id: str):
    """
    Scan for events that should generate notifications:
    1. Upcoming deadlines (calendar_events due in 1-3 days)
    2. Hermes auto-moves (kanban_card_logs moved_by_hermes=true, last 24h)
    3. High-priority emails (email_intakes priority=urgent, last 24h)
    """
    now     = datetime.utcnow()
    in_3d   = now + timedelta(days=3)
    since   = now - timedelta(hours=24)

    with get_conn(firm_id) as conn:

        # 1. Upcoming deadlines
        try:
            deadlines = conn.execute(
                """
                SELECT id, title, due_date, event_type, matter_id
                FROM calendar_events
                WHERE firm_id=%s
                  AND due_date BETWEEN %s AND %s
                  AND status != 'completed'
                """,
                (firm_id, now.date(), in_3d.date())
            ).fetchall()

            for d in deadlines:
                d = dict(d)
                due = d["due_date"]
                days_away = (due - now.date()).days if hasattr(due, 'year') else 0
                urgency = "today" if days_away == 0 else f"in {days_away} day{'s' if days_away != 1 else ''}"

                # Check if we already notified about this deadline today
                existing = conn.execute(
                    """SELECT 1 FROM notifications
                       WHERE firm_id=%s AND type='deadline'
                         AND title LIKE %s
                         AND created_at > %s""",
                    (firm_id, f"%{d['title'][:30]}%", since.isoformat())
                ).fetchone()

                if not existing:
                    conn.execute(
                        """INSERT INTO notifications (firm_id, type, title, body, link)
                           VALUES (%s, 'deadline', %s, %s, %s)""",
                        (firm_id,
                         f"Deadline {urgency}: {d['title']}",
                         f"{d['title']} is due {urgency}.",
                         f"/calendar")
                    )
        except (psycopg2.Error, KeyError, ValueError, TypeError) as e:
            log.warning(f"Deadline notification error: {e}")

        # 2. Hermes auto-moves (last 24h)
        try:
            hermes_moves = conn.execute(
                """
                SELECT kl.card_id, kl.case_id, kl.from_column, kl.to_column,
                       kl.hermes_reason, kl.moved_at, kc.title AS card_title
                FROM kanban_card_logs kl
                JOIN kanban_cards kc ON kc.id = kl.card_id
                WHERE kl.firm_id=%s
                  AND kl.moved_by_hermes=TRUE
                  AND kl.moved_at > %s
                """,
                (firm_id, since.isoformat())
            ).fetchall()

            for m in hermes_moves:
                m = dict(m)
                existing = conn.execute(
                    """SELECT 1 FROM notifications
                       WHERE firm_id=%s AND type='hermes'
                         AND body LIKE %s
                         AND created_at > %s""",
                    (firm_id, f"%card {m['card_id']}%", since.isoformat())
                ).fetchone()

                if not existing:
                    to_col = m["to_column"].replace("_", " ").title()
                    conn.execute(
                        """INSERT INTO notifications (firm_id, type, title, body, link)
                           VALUES (%s, 'hermes', %s, %s, %s)""",
                        (firm_id,
                         f"[Hermes] Moved: {m['card_title'][:50]}",
                         f"Card moved to {to_col}. Reason: {m['hermes_reason'] or 'status change detected'}. card {m['card_id']}",
                         f"/matters/{m['case_id']}")
                    )
        except (psycopg2.Error, KeyError, ValueError, TypeError) as e:
            log.warning(f"Hermes notification error: {e}")

        # 3. High-priority emails (last 24h)
        try:
            urgent_emails = conn.execute(
                """
                SELECT id, from_address, subject, priority, ingested_at
                FROM email_intakes
                WHERE firm_id=%s
                  AND priority IN ('urgent', 'high')
                  AND ingested_at > %s
                """,
                (firm_id, since.isoformat())
            ).fetchall()

            for e in urgent_emails:
                e = dict(e)
                existing = conn.execute(
                    """SELECT 1 FROM notifications
                       WHERE firm_id=%s AND type='email'
                         AND body LIKE %s
                         AND created_at > %s""",
                    (firm_id, f"%{e['id']}%", since.isoformat())
                ).fetchone()

                if not existing:
                    priority = e["priority"].upper()
                    conn.execute(
                        """INSERT INTO notifications (firm_id, type, title, body, link)
                           VALUES (%s, 'email', %s, %s, %s)""",
                        (firm_id,
                         f"📧 {priority} email: {(e['subject'] or 'No subject')[:50]}",
                         f"From {e['from_address']}. ID: {e['id']}",
                         "/email-inbox")
                    )
        except (psycopg2.Error, KeyError, ValueError, TypeError) as e:
            log.warning(f"Email notification error: {e}")

    log.info(f"[Notifications] Generated for firm {firm_id}")
