"""
backend/demo1/routers/workflows_router.py
==========================================
Automated Workflows: trigger-action rules for repetitive firm tasks.
e.g. "When case status changes to Filed, send client an email."

Referenced by frontend/paraiq-vue/src/views/workflows/WorkflowsView.vue
Table: workflows (RLS-protected via app.current_firm_id, see migrations/004)

SECURITY: firm_id is derived exclusively from a validated JWT via
get_current_firm_id (auth.py). It does NOT fall back to request.state.firm_id,
which TenantMiddleware silently defaults to "default" when no/invalid JWT is
present. An X-API-Key alone (no user login) is NOT sufficient to read or
write tenant-scoped workflow data.
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["Workflows"])


# ── Pydantic models ──────────────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    name: str
    trigger_event: str
    trigger_conditions: Optional[dict] = {}
    action_type: str
    action_payload: Optional[dict] = {}


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/")
def list_workflows(firm_id: str = Depends(get_current_firm_id)):
    """List all workflows for the authenticated firm. Requires a valid JWT."""
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT id, name, trigger_event, trigger_conditions, action_type, "
            "action_payload, is_active, created_at FROM workflows ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/")
def create_workflow(body: WorkflowCreate, firm_id: str = Depends(get_current_firm_id)):
    """Create a new workflow rule for the authenticated firm. Requires a valid JWT."""
    if not body.name.strip():
        raise HTTPException(400, "Workflow name is required")
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "INSERT INTO workflows (firm_id, name, trigger_event, trigger_conditions, "
            "action_type, action_payload) VALUES (%s, %s, %s, %s, %s, %s) "
            "RETURNING id, name, trigger_event, trigger_conditions, action_type, "
            "action_payload, is_active, created_at",
            (
                firm_id,
                body.name.strip(),
                body.trigger_event,
                json.dumps(body.trigger_conditions or {}),
                body.action_type,
                json.dumps(body.action_payload or {}),
            ),
        ).fetchone()
        conn.commit()
    return dict(row)


@router.delete("/{workflow_id}")
def delete_workflow(workflow_id: int, firm_id: str = Depends(get_current_firm_id)):
    """Delete a workflow. Requires a valid JWT; RLS ensures only the owning
    firm's row can be deleted even if this check were somehow bypassed."""
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "DELETE FROM workflows WHERE id = %s RETURNING id", (workflow_id,)
        ).fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, f"Workflow {workflow_id} not found")
    return {"success": True, "deleted_id": workflow_id}
