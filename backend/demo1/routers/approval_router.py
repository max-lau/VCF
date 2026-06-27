"""
approval_router.py — Unified Approval Queue
============================================
All semi-automatic actions feed this queue.
Attorneys resolve pending decisions in one screen.

Mount in main.py:
    from backend.demo1.routers.approval_router import router as approval_router
    app.include_router(approval_router, prefix="/approvals", tags=["approvals"])
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.demo1.auth import get_current_user, get_current_firm_id
from backend.demo1.pg import get_conn

router = APIRouter()
log    = logging.getLogger(__name__)


# ── Pydantic models ───────────────────────────────────────────────────────────

class ApprovalCreate(BaseModel):
    item_type:      str
    title:          str
    context_json:   Optional[dict] = None
    recommended:    Optional[str]  = None
    priority:       int            = 3
    related_matter: Optional[int]  = None
    created_by:     str            = "system"
    due_by:         Optional[str]  = None

class ApprovalResolve(BaseModel):
    action:          str            # 'approved' | 'rejected'
    resolution_note: Optional[str] = None


# ── Helper: create queue item (called internally by other modules) ─────────────

def enqueue(firm_id: str, item_type: str, title: str,
            context_json: dict = None, recommended: str = None,
            priority: int = 3, related_matter: int = None,
            created_by: str = "system", due_by=None):
    """
    Called by any module to add an item to the approval queue.
    Example:
        from backend.demo1.routers.approval_router import enqueue
        enqueue(firm_id, 'matter_assignment', 'Assign Chen v. Marsh → thornton',
                context_json={...}, recommended='assign_to_thornton', priority=2)
    """
    try:
        with get_conn(firm_id) as conn:
            conn.execute("""
                INSERT INTO approval_queue
                  (firm_id, item_type, title, context_json, recommended,
                   priority, related_matter, created_by, due_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                firm_id, item_type, title,
                __import__('json').dumps(context_json) if context_json else None,
                recommended, priority, related_matter, created_by, due_by
            ))
        log.info(f"[ApprovalQueue] Enqueued: {item_type} for {firm_id}")
    except Exception as e:
        log.error(f"[ApprovalQueue] Enqueue failed: {e}")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
def list_queue(
    status:   str = "pending",
    priority: Optional[int] = None,
    limit:    int = 50,
    firm_id:  str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """List approval queue items for the firm, newest/most urgent first."""
    sql    = """
        SELECT aq.*, c.case_number, c.client_name
        FROM approval_queue aq
        LEFT JOIN cases c ON c.id = aq.related_matter AND c.firm_id = aq.firm_id
        WHERE aq.firm_id = %s AND aq.status = %s
    """
    params = [firm_id, status]

    if priority:
        sql += " AND aq.priority = %s"
        params.append(priority)

    sql += " ORDER BY aq.priority ASC, aq.due_by ASC NULLS LAST, aq.created_at ASC LIMIT %s"
    params.append(limit)

    with get_conn(firm_id) as conn:
        rows = conn.execute(sql, params).fetchall()
        pending_count = conn.execute(
            "SELECT COUNT(*) AS n FROM approval_queue WHERE firm_id=%s AND status='pending'",
            (firm_id,)
        ).fetchone()["n"]

    items = []
    for r in rows:
        d = dict(r)
        for f in ["created_at", "resolved_at", "due_by"]:
            if d.get(f) and hasattr(d[f], "isoformat"):
                d[f] = d[f].isoformat()
        if d.get("context_json") and isinstance(d["context_json"], str):
            import json
            try:
                d["context_json"] = json.loads(d["context_json"])
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                log.warning(f"[ApprovalQueue] context_json parse failed for item {d.get('id')}: {e}")
        items.append(d)

    return {"items": items, "pending_count": pending_count}


@router.get("/{item_id}")
def get_item(
    item_id: int,
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        row = conn.execute(
            """SELECT aq.*, c.case_number, c.client_name
               FROM approval_queue aq
               LEFT JOIN cases c ON c.id = aq.related_matter
               WHERE aq.id=%s AND aq.firm_id=%s""",
            (item_id, firm_id)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Item not found")
    d = dict(row)
    for f in ["created_at", "resolved_at", "due_by"]:
        if d.get(f) and hasattr(d[f], "isoformat"):
            d[f] = d[f].isoformat()
    return d


@router.post("/{item_id}/resolve")
def resolve_item(
    item_id: int,
    body:    ApprovalResolve,
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    if body.action not in ("approved", "rejected"):
        raise HTTPException(400, "action must be 'approved' or 'rejected'")

    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT id, status, item_type FROM approval_queue WHERE id=%s AND firm_id=%s",
            (item_id, firm_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        if row["status"] != "pending":
            raise HTTPException(409, f"Item already {row['status']}")

        conn.execute("""
            UPDATE approval_queue
               SET status=%s, resolved_by=%s, resolved_at=%s, resolution_note=%s
             WHERE id=%s AND firm_id=%s
        """, (
            body.action,
            user["id"],
            datetime.now(timezone.utc),
            body.resolution_note,
            item_id, firm_id
        ))

    log.info(f"[ApprovalQueue] {body.action} item {item_id} by user {user['id']}")
    return {"ok": True, "status": body.action}


@router.post("/{item_id}/expire")
def expire_item(
    item_id: int,
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    """Manually expire a stale item."""
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE approval_queue SET status='expired' WHERE id=%s AND firm_id=%s AND status='pending'",
            (item_id, firm_id)
        )
    return {"ok": True}


@router.get("/stats/summary")
def queue_stats(
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        by_status = conn.execute("""
            SELECT status, COUNT(*) AS cnt
            FROM approval_queue WHERE firm_id=%s
            GROUP BY status
        """, (firm_id,)).fetchall()

        by_type = conn.execute("""
            SELECT item_type, COUNT(*) AS cnt
            FROM approval_queue WHERE firm_id=%s AND status='pending'
            GROUP BY item_type ORDER BY cnt DESC
        """, (firm_id,)).fetchall()

        overdue = conn.execute("""
            SELECT COUNT(*) AS n FROM approval_queue
            WHERE firm_id=%s AND status='pending'
              AND due_by IS NOT NULL AND due_by < NOW()
        """, (firm_id,)).fetchone()["n"]

    return {
        "by_status": [dict(r) for r in by_status],
        "pending_by_type": [dict(r) for r in by_type],
        "overdue": overdue,
    }
