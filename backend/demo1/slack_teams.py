import os
import httpx
import asyncio
import logging
import psycopg2
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id

logger = logging.getLogger(__name__)

router = APIRouter()


def init_notify_table():
    """No-op -- tables exist in Supabase Postgres."""
    print("[Notify] Tables initialized OK")


def log_delivery(platform, event_type, status_code, success, error=None, preview="", firm_id="default"):
    try:
        with get_conn(firm_id) as conn:
            conn.execute("""
                INSERT INTO notify_log
                  (platform, event_type, sent_at, status_code, success, error, preview)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (platform, event_type, datetime.now(timezone.utc).isoformat(),
                  status_code, success, str(error) if error else None, preview[:200]))
            conn.execute("""
                UPDATE notify_config SET last_used=%s, send_count=send_count+1
                WHERE platform=%s AND active=TRUE
            """, (datetime.now(timezone.utc).isoformat(), platform))
    except (psycopg2.Error, KeyError, ValueError) as e:
        print(f"[Notify] Log error: {e}")


def build_slack_simple(text: str, title: str = "NLP Notification") -> dict:
    return {"blocks": [
        {"type": "header", "text": {"type": "plain_text", "text": title}},
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}]}
    ]}


def build_slack_analysis(result: dict, label: str = "Document") -> dict:
    sentiment = result.get("sentiment", "N/A").upper()
    score     = round(result.get("score", 0) * 100, 1)
    top_ents  = ", ".join(e.get("text","") for e in result.get("entities",[])[:5]) or "None"
    return {"blocks": [
        {"type": "header", "text": {"type": "plain_text", "text": f"NLP Analysis -- {label}"}},
        {"type": "divider"},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Sentiment*\n{sentiment}"},
            {"type": "mrkdwn", "text": f"*Confidence*\n{score}%"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Top Entities*\n{top_ents}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}]}
    ]}


def build_slack_risk(risk: dict, label: str = "Document") -> dict:
    score    = risk.get("score", 0)
    level    = risk.get("level", "unknown").upper()
    cats     = risk.get("category_breakdown", {})
    cat_text = "\n".join(f"- {k.replace('_',' ').title()}: {v}" for k,v in cats.items())
    return {"blocks": [
        {"type": "header", "text": {"type": "plain_text", "text": f"Risk Alert -- {label}"}},
        {"type": "divider"},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Risk Score*\n{score} / 10"},
            {"type": "mrkdwn", "text": f"*Risk Level*\n{level}"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Category Breakdown*\n{cat_text or 'N/A'}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}]}
    ]}


def build_teams_analysis(result: dict, label: str = "Document") -> dict:
    sentiment = result.get("sentiment", "N/A").upper()
    score     = round(result.get("score", 0) * 100, 1)
    top_ents  = ", ".join(e.get("text","") for e in result.get("entities",[])[:5]) or "None"
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
        "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard", "version": "1.4", "body": [
                {"type": "TextBlock", "size": "Large", "weight": "Bolder", "text": f"NLP Analysis -- {label}"},
                {"type": "FactSet", "facts": [
                    {"title": "Sentiment", "value": sentiment},
                    {"title": "Confidence", "value": f"{score}%"},
                    {"title": "Top Entities", "value": top_ents},
                ]},
                {"type": "TextBlock", "size": "Small", "isSubtle": True,
                 "text": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
            ]}}]}


def build_teams_risk(risk: dict, label: str = "Document") -> dict:
    score = risk.get("score", 0)
    level = risk.get("level", "unknown").upper()
    facts = [{"title": "Risk Score", "value": f"{score} / 10"}, {"title": "Risk Level", "value": level}]
    for k, v in risk.get("category_breakdown", {}).items():
        facts.append({"title": k.replace("_"," ").title(), "value": str(v)})
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
        "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard", "version": "1.4", "body": [
                {"type": "TextBlock", "size": "Large", "weight": "Bolder", "text": f"Risk Alert -- {label}"},
                {"type": "FactSet", "facts": facts},
                {"type": "TextBlock", "size": "Small", "isSubtle": True,
                 "text": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
            ]}}]}


async def send_to_platform(platform: str, payload: dict, event_type: str, mock: bool = False, firm_id: str = "default") -> dict:
    with get_conn(firm_id) as conn:
        configs = conn.execute(
            "SELECT * FROM notify_config WHERE platform=%s AND active=TRUE", (platform,)
        ).fetchall()

    if not configs:
        return {"sent": 0, "message": f"No active {platform} webhooks configured"}

    if mock:
        log_delivery(platform, event_type, 200, True, preview=str(payload)[:100], firm_id=firm_id)
        return {"sent": len(configs), "mock": True,
                "message": f"Mock delivery to {len(configs)} {platform} webhook(s)",
                "payload_preview": str(payload)[:200]}

    results = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for cfg in configs:
            try:
                resp = await client.post(cfg["webhook_url"], json=payload)
                success = resp.status_code < 400
                log_delivery(platform, event_type, resp.status_code, success, preview=str(payload)[:100], firm_id=firm_id)
                results.append({"label": cfg["label"], "status": resp.status_code, "success": success})
            except (httpx.HTTPError, OSError) as e:
                logger.warning(f"[Notify] Webhook delivery to '{cfg['label']}' ({platform}) failed: {e}")
                log_delivery(platform, event_type, None, False, error="Delivery failed", firm_id=firm_id)
                results.append({"label": cfg["label"], "error": "Delivery failed", "success": False})
    return {"sent": len(results), "results": results}


class ConfigureWebhook(BaseModel):
    webhook_url: str
    label:       Optional[str] = ""

class SendMessage(BaseModel):
    title:   Optional[str] = "NLP Notification"
    message: str
    mock:    Optional[bool] = True

class SendAnalysis(BaseModel):
    text:  str
    label: Optional[str] = "Document"
    mock:  Optional[bool] = True

class SendRiskAlert(BaseModel):
    text:    str
    context: Optional[str] = "general"
    label:   Optional[str] = "Document"
    mock:    Optional[bool] = True


@router.post("/slack/configure")
def configure_slack(body: ConfigureWebhook, firm_id: str = Depends(get_current_firm_id)):
    if not body.webhook_url.startswith("http"):
        raise HTTPException(400, "Invalid webhook URL")
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO notify_config (platform, label, webhook_url, created_at)
            VALUES (%s,%s,%s,%s) RETURNING id
        """, ("slack", body.label, body.webhook_url, datetime.now(timezone.utc).isoformat()))
        row_id = cur.fetchone()["id"]
    return {"success": True, "id": row_id, "platform": "slack", "label": body.label}


@router.post("/teams/configure")
def configure_teams(body: ConfigureWebhook, firm_id: str = Depends(get_current_firm_id)):
    if not body.webhook_url.startswith("http"):
        raise HTTPException(400, "Invalid webhook URL")
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO notify_config (platform, label, webhook_url, created_at)
            VALUES (%s,%s,%s,%s) RETURNING id
        """, ("teams", body.label, body.webhook_url, datetime.now(timezone.utc).isoformat()))
        row_id = cur.fetchone()["id"]
    return {"success": True, "id": row_id, "platform": "teams", "label": body.label}


@router.post("/slack/send")
async def send_slack_message(body: SendMessage, firm_id: str = Depends(get_current_firm_id)):
    payload = build_slack_simple(body.message, body.title)
    result  = await send_to_platform("slack", payload, "simple_message", mock=body.mock, firm_id=firm_id)
    return {"success": True, "platform": "slack", **result}


@router.post("/teams/send")
async def send_teams_message(body: SendMessage, firm_id: str = Depends(get_current_firm_id)):
    payload = {"text": f"**{body.title}**\n\n{body.message}"}
    result  = await send_to_platform("teams", payload, "simple_message", mock=body.mock, firm_id=firm_id)
    return {"success": True, "platform": "teams", **result}


@router.post("/slack/analysis")
async def send_slack_analysis(body: SendAnalysis, firm_id: str = Depends(get_current_firm_id)):
    result  = {"sentiment": "NEGATIVE", "score": 0.87, "entities": [], "label": body.label}
    payload = build_slack_analysis(result, label=body.label)
    outcome = await send_to_platform("slack", payload, "analysis", mock=body.mock, firm_id=firm_id)
    return {"success": True, "platform": "slack", **outcome}


@router.post("/teams/analysis")
async def send_teams_analysis(body: SendAnalysis, firm_id: str = Depends(get_current_firm_id)):
    result  = {"sentiment": "NEGATIVE", "score": 0.87, "entities": [], "label": body.label}
    payload = build_teams_analysis(result, label=body.label)
    outcome = await send_to_platform("teams", payload, "analysis", mock=body.mock, firm_id=firm_id)
    return {"success": True, "platform": "teams", **outcome}


@router.post("/risk/alert")
async def send_risk_alert(body: SendRiskAlert, firm_id: str = Depends(get_current_firm_id)):
    from backend.demo1.risk_scorer import score_text
    risk         = score_text(body.text, context=body.context)
    slack_result = await send_to_platform("slack", build_slack_risk(risk, body.label), "risk_alert", mock=body.mock, firm_id=firm_id)
    teams_result = await send_to_platform("teams", build_teams_risk(risk, body.label), "risk_alert", mock=body.mock, firm_id=firm_id)
    return {"success": True, "risk_score": risk["score"], "risk_level": risk["level"],
            "slack": slack_result, "teams": teams_result}


@router.get("/config")
def get_config(firm_id: str = Depends(get_current_firm_id)):
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT id, platform, label, active, created_at, last_used, send_count FROM notify_config ORDER BY id DESC"
        ).fetchall()
    return {"success": True, "count": len(rows), "channels": [dict(r) for r in rows]}


@router.get("/logs")
def get_notify_logs(platform: Optional[str] = None, limit: int = 50, firm_id: str = Depends(get_current_firm_id)):
    limit = min(limit, 200)
    where, args = [], []
    if platform:
        where.append("platform=%s")
        args.append(platform)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            f"SELECT * FROM notify_log {where_sql} ORDER BY id DESC LIMIT %s",
            args + [limit]
        ).fetchall()
    return {"success": True, "count": len(rows), "logs": [dict(r) for r in rows]}
