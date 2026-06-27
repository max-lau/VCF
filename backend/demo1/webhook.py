import os
import httpx
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_EVENTS = {
    "high_risk_document",
    "case_created",
    "contradiction_found",
    "citation_resolved",
}


def init_webhook_table():
    """No-op -- tables exist in Supabase Postgres."""
    print("[Webhooks] Tables initialized OK")


class RegisterWebhook(BaseModel):
    event: str
    url:   str
    label: Optional[str] = ""

class TestWebhook(BaseModel):
    subscription_id: int

class FireEventBody(BaseModel):
    event:   str
    payload: dict


async def deliver_webhook(subscription_id: int, event: str, url: str, payload: dict, firm_id: str = "default"):
    fired_at    = datetime.now(timezone.utc).isoformat()
    payload_str = str(payload)[:200]
    status_code = None
    success     = False
    error       = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={"event": event, "fired_at": fired_at, "payload": payload,
                      "source": "ParaIQ Legal API"},
                headers={"Content-Type": "application/json", "X-ParaIQ-Event": event}
            )
            status_code = resp.status_code
            success     = resp.status_code < 400
    except httpx.TimeoutException:
        error = "Timeout after 10s"
    except (httpx.HTTPError, OSError) as e:
        logger.warning(f"[Webhooks] Delivery to {url} failed: {e}")
        error = "Webhook delivery failed"

    try:
        with get_conn(firm_id) as conn:
            conn.execute("""
                INSERT INTO webhook_log
                  (subscription_id, event, fired_at, status_code, success, error, payload_preview)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (subscription_id, event, fired_at, status_code, success, error, payload_str))
            conn.execute("""
                UPDATE webhook_subscriptions
                SET last_fired=%s, fire_count=fire_count+1, last_status=%s
                WHERE id=%s
            """, (fired_at, status_code, subscription_id))
    except Exception as e:
        print(f"[Webhooks] Log error: {e}")


async def fire_event(event: str, payload: dict, firm_id: str = "default"):
    if event not in VALID_EVENTS:
        return
    with get_conn(firm_id) as conn:
        subs = conn.execute(
            "SELECT id, url FROM webhook_subscriptions WHERE event=%s AND active=TRUE",
            (event,)
        ).fetchall()
    tasks = [deliver_webhook(row["id"], event, row["url"], payload, firm_id=firm_id) for row in subs]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def fire_event_sync(event: str, payload: dict, background_tasks: BackgroundTasks, firm_id: str = "default"):
    background_tasks.add_task(fire_event, event, payload, firm_id)


@router.post("/subscribe")
def register_webhook(body: RegisterWebhook, firm_id: str = Depends(get_current_firm_id)):
    if body.event not in VALID_EVENTS:
        raise HTTPException(400, f"Invalid event. Valid events: {sorted(VALID_EVENTS)}")
    if not body.url.startswith("http"):
        raise HTTPException(400, "URL must start with http:// or https://")
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO webhook_subscriptions (event, url, label, created_at)
            VALUES (%s,%s,%s,%s) RETURNING id
        """, (body.event, body.url, body.label, datetime.now(timezone.utc).isoformat()))
        sub_id = cur.fetchone()["id"]
    return {"success": True, "subscription_id": sub_id, "event": body.event,
            "url": body.url, "label": body.label}


@router.get("/subscriptions")
def list_subscriptions(event: Optional[str] = None, firm_id: str = Depends(get_current_firm_id)):
    where, args = [], []
    if event:
        where.append("event=%s")
        args.append(event)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            f"SELECT * FROM webhook_subscriptions {where_sql} ORDER BY id DESC", args
        ).fetchall()
    return {"success": True, "count": len(rows), "subscriptions": [dict(r) for r in rows]}


@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: int, firm_id: str = Depends(get_current_firm_id)):
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE webhook_subscriptions SET active=FALSE WHERE id=%s", (sub_id,)
        )
    return {"success": True, "message": f"Subscription {sub_id} deactivated"}


@router.post("/test/{sub_id}")
async def test_webhook(sub_id: int, firm_id: str = Depends(get_current_firm_id)):
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT * FROM webhook_subscriptions WHERE id=%s", (sub_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, f"Subscription {sub_id} not found")
    await deliver_webhook(sub_id, row["event"], row["url"],
        {"test": True, "message": "Test webhook from ParaIQ", "subscription_id": sub_id}, firm_id=firm_id)
    return {"success": True, "message": f"Test webhook fired to {row['url']}"}


@router.post("/fire")
async def manually_fire_event(body: FireEventBody, firm_id: str = Depends(get_current_firm_id)):
    if body.event not in VALID_EVENTS:
        raise HTTPException(400, f"Invalid event. Valid: {sorted(VALID_EVENTS)}")
    await fire_event(body.event, body.payload, firm_id=firm_id)
    return {"success": True, "event": body.event, "message": "Event fired to all active subscribers"}


@router.get("/logs")
def webhook_logs(subscription_id: Optional[int] = None, limit: int = 50, firm_id: str = Depends(get_current_firm_id)):
    limit = min(limit, 200)
    where, args = [], []
    if subscription_id:
        where.append("subscription_id=%s")
        args.append(subscription_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            f"SELECT * FROM webhook_log {where_sql} ORDER BY id DESC LIMIT %s",
            args + [limit]
        ).fetchall()
    return {"success": True, "count": len(rows), "logs": [dict(r) for r in rows]}


@router.get("/events")
def list_events():
    return {"events": [
        {"event": "high_risk_document",  "description": "Fired when document risk score >= 7.0"},
        {"event": "case_created",         "description": "Fired when a new case is created"},
        {"event": "contradiction_found",  "description": "Fired when contradictions are detected"},
        {"event": "citation_resolved",    "description": "Fired when a citation is resolved"},
    ]}
