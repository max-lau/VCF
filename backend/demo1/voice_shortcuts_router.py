"""
voice_shortcuts_router.py
=========================
CRUD endpoints for user-defined voice shortcuts.
GET    /voice/shortcuts          - list user's shortcuts
POST   /voice/shortcuts          - create a shortcut
PUT    /voice/shortcuts/{id}     - update a shortcut
DELETE /voice/shortcuts/{id}     - delete a shortcut
GET    /voice/shortcuts/actions  - list all valid action names
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import json

from .pg import get_conn, db_dep
from .auth import get_current_user, get_current_firm_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/voice/shortcuts", tags=["voice-shortcuts"])

# Full list of valid actions from voice_router ROUTE_MAP + compound commands
VALID_ACTIONS = [
    "get_deadlines", "get_upcoming_calendar", "get_calendar_types",
    "get_cases_stats", "search_cases", "get_contacts",
    "get_discovery_stats", "get_discovery_queue", "get_discovery_duplicates",
    "get_discovery_catalog", "get_risk_signals", "get_legal_bert_status",
    "get_intake_history", "get_privilege_stats", "get_privilege_log",
    "get_reports_list", "get_deposition_stats", "get_depositions",
    "get_motion_stats", "get_motions", "get_contract_stats", "get_contracts",
    "get_research", "get_dashboard_stats", "get_audit_logs", "get_audit_stats",
    "get_health", "get_api_stats", "screen_all_discovery",
    "get_matter_kanban", "get_matter_timeline", "get_matter_documents",
    "get_matter_notes", "get_matter_intel", "add_matter_kanban_card",
    "get_workload_today", "get_case_intelligence",
]

class ShortcutCreate(BaseModel):
    phrase: str
    action: str
    params: dict = {}
    description: Optional[str] = None

class ShortcutUpdate(BaseModel):
    phrase: Optional[str] = None
    action: Optional[str] = None
    params: Optional[dict] = None
    description: Optional[str] = None


@router.get("/actions")
def list_actions():
    """Return all valid action names the user can map to."""
    return {"actions": VALID_ACTIONS}


@router.get("")
def list_shortcuts(
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """SELECT id, phrase, action, params, description, created_at
               FROM voice_shortcuts
               WHERE firm_id=%s AND user_id=%s
               ORDER BY created_at DESC""",
            (firm_id, user["id"])
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("")
def create_shortcut(
    body: ShortcutCreate,
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    if body.action not in VALID_ACTIONS:
        raise HTTPException(400, f"Invalid action '{body.action}'. Use GET /voice/shortcuts/actions for valid options.")
    phrase = body.phrase.strip().lower()
    if len(phrase) < 2:
        raise HTTPException(400, "Phrase must be at least 2 characters.")
    if len(phrase) > 100:
        raise HTTPException(400, "Phrase must be under 100 characters.")

    with get_conn(firm_id) as conn:
        existing = conn.execute(
            "SELECT id FROM voice_shortcuts WHERE firm_id=%s AND user_id=%s AND phrase=%s",
            (firm_id, user["id"], phrase)
        ).fetchone()
        if existing:
            raise HTTPException(409, f"Shortcut '{phrase}' already exists.")
        row = conn.execute(
            """INSERT INTO voice_shortcuts (firm_id, user_id, phrase, action, params, description)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id, phrase, action, params, description, created_at""",
            (firm_id, user["id"], phrase, body.action,
             json.dumps(body.params), body.description)
        ).fetchone()
    return dict(row)


@router.put("/{shortcut_id}")
def update_shortcut(
    shortcut_id: int,
    body: ShortcutUpdate,
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        existing = conn.execute(
            "SELECT * FROM voice_shortcuts WHERE id=%s AND firm_id=%s AND user_id=%s",
            (shortcut_id, firm_id, user["id"])
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Shortcut not found.")

        existing = dict(existing)
        new_phrase      = body.phrase.strip().lower() if body.phrase else existing["phrase"]
        new_action      = body.action if body.action else existing["action"]
        new_params      = body.params if body.params is not None else existing["params"]
        new_description = body.description if body.description is not None else existing["description"]

        if new_action not in VALID_ACTIONS:
            raise HTTPException(400, f"Invalid action '{new_action}'.")

        row = conn.execute(
            """UPDATE voice_shortcuts
               SET phrase=%s, action=%s, params=%s, description=%s
               WHERE id=%s AND firm_id=%s AND user_id=%s
               RETURNING id, phrase, action, params, description, created_at""",
            (new_phrase, new_action, json.dumps(new_params),
             new_description, shortcut_id, firm_id, user["id"])
        ).fetchone()
    return dict(row)


@router.delete("/{shortcut_id}")
def delete_shortcut(
    shortcut_id: int,
    firm_id: str = Depends(get_current_firm_id),
    user=Depends(get_current_user),
):
    with get_conn(firm_id) as conn:
        existing = conn.execute(
            "SELECT id FROM voice_shortcuts WHERE id=%s AND firm_id=%s AND user_id=%s",
            (shortcut_id, firm_id, user["id"])
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Shortcut not found.")
        conn.execute(
            "DELETE FROM voice_shortcuts WHERE id=%s AND firm_id=%s AND user_id=%s",
            (shortcut_id, firm_id, user["id"])
        )
    return {"deleted": shortcut_id}
