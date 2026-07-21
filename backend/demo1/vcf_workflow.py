"""
backend/demo1/vcf_workflow.py
─────────────────────────────
Claim lifecycle stage machine, checklist, and auto-deadline generation
for VCFClaimsIQ.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.demo1.pg import get_conn
from backend.demo1.acp_vcf_config import VCF_DEADLINES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["VCF Workflow"])


# ── Stage / deadline configuration ────────────────────────────────────────────

CLAIM_STAGES = [
    "intake",
    "eligibility_review",
    "document_gathering",
    "vcf_account_created",
    "claim_submitted",
    "under_review",
    "award_determination",
    "disbursement",
    "closed",
]

# When entering a stage, create these deadlines (deadline_type -> days from now).
STAGE_DEADLINES: dict[str, list[tuple[str, int]]] = {
    "eligibility_review": [("missing_info_response", VCF_DEADLINES["missing_info"])],
    "under_review":       [("award_processing", VCF_DEADLINES["award_calc"])],
}

# Required documents per stage.
STAGE_CHECKLIST: dict[str, list[tuple[str, str]]] = {
    "intake": [
        ("retainer", "Signed retainer agreement"),
        ("intake_form", "Completed VCF intake questionnaire"),
        ("id_proof", "Government-issued ID"),
    ],
    "eligibility_review": [
        ("presence_proof", "Proof of presence in NYC exposure zone"),
        ("medical_record", "Medical record showing certified condition"),
    ],
    "document_gathering": [
        ("wtc_health_program", "WTC Health Program documentation"),
        ("financial_docs", "W-2 / tax returns / lost earnings proof"),
        ("medicare_lien", "Medicare lien information"),
        ("medicaid_lien", "Medicaid lien information"),
    ],
    "vcf_account_created": [
        ("vcf_credentials", "VCF.gov credentials stored securely"),
    ],
    "claim_submitted": [
        ("submission_confirmation", "VCF claim submission confirmation"),
    ],
    "award_determination": [
        ("award_letter", "VCF award determination letter"),
    ],
    "disbursement": [
        ("banking_info", "Client banking / payment information"),
        ("lien_resolution", "Medicare/Medicaid/Workers Comp liens resolved"),
    ],
}


# ── Pydantic models ───────────────────────────────────────────────────────────

class StageTransitionBody(BaseModel):
    to_stage: str
    note: Optional[str] = ""


class ChecklistItemUpdate(BaseModel):
    item_key: str
    status: str  # pending | complete | not_applicable
    note: Optional[str] = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _today() -> date:
    return datetime.now().date()


def _ensure_checklist(conn, firm_id: str, case_id: int, stage: str) -> None:
    """Seed checklist items for a stage if they don't already exist."""
    items = STAGE_CHECKLIST.get(stage, [])
    for key, label in items:
        conn.execute(
            """
            INSERT INTO claim_checklists (firm_id, case_id, stage, item_key, label, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
            ON CONFLICT (firm_id, case_id, stage, item_key) DO NOTHING
            """,
            (firm_id, case_id, stage, key, label),
        )


def _create_stage_deadlines(conn, firm_id: str, case_id: int, to_stage: str) -> None:
    for deadline_type, days in STAGE_DEADLINES.get(to_stage, []):
        due = _today() + timedelta(days=days)
        conn.execute(
            """
            INSERT INTO vcf_deadlines (firm_id, case_id, deadline_type, due_date, status, description)
            VALUES (%s, %s, %s, %s, 'pending', %s)
            ON CONFLICT DO NOTHING
            """,
            (firm_id, case_id, deadline_type, due,
             f"Auto-generated on stage transition to {to_stage}"),
        )


def _record_stage_history(conn, firm_id: str, case_id: int, from_stage: Optional[str],
                          to_stage: str, changed_by: str, note: str) -> None:
    conn.execute(
        """
        INSERT INTO claim_stage_history (firm_id, case_id, from_stage, to_stage, changed_by, note)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (firm_id, case_id, from_stage, to_stage, changed_by, note),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/vcf/cases/{case_id}/stage")
async def transition_stage(case_id: int, body: StageTransitionBody, request: Request):
    """Transition a claim to a new stage, seed checklist, and create deadlines."""
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    user_id = str(getattr(request.state, "user_id", "") or "system")

    if body.to_stage not in CLAIM_STAGES:
        raise HTTPException(400, f"Invalid stage. Must be one of: {', '.join(CLAIM_STAGES)}")

    with get_conn(firm_id) as conn:
        case = conn.execute(
            "SELECT id, claim_stage FROM cases WHERE id = %s AND firm_id = %s",
            (case_id, firm_id),
        ).fetchone()
        if not case:
            raise HTTPException(404, "Claim not found")

        from_stage = case["claim_stage"]
        if from_stage == body.to_stage:
            raise HTTPException(400, "Claim is already in this stage")

        conn.execute(
            "UPDATE cases SET claim_stage = %s, updated_at = NOW() WHERE id = %s AND firm_id = %s",
            (body.to_stage, case_id, firm_id),
        )
        _record_stage_history(conn, firm_id, case_id, from_stage, body.to_stage, user_id, body.note or "")
        _ensure_checklist(conn, firm_id, case_id, body.to_stage)
        _create_stage_deadlines(conn, firm_id, case_id, body.to_stage)
        conn.commit()

    return {
        "success": True,
        "case_id": case_id,
        "from_stage": from_stage,
        "to_stage": body.to_stage,
    }


@router.get("/vcf/cases/{case_id}/stages")
async def list_stage_history(case_id: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """
            SELECT id, from_stage, to_stage, changed_by, note, created_at
            FROM claim_stage_history
            WHERE case_id = %s AND firm_id = %s
            ORDER BY created_at DESC
            """,
            (case_id, firm_id),
        ).fetchall()
    return {"success": True, "history": [dict(r) for r in rows]}


@router.get("/vcf/cases/{case_id}/checklist")
async def get_checklist(case_id: int, request: Request, stage: Optional[str] = None):
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    with get_conn(firm_id) as conn:
        # If stage not provided, use current claim stage.
        if stage is None:
            row = conn.execute(
                "SELECT claim_stage FROM cases WHERE id = %s AND firm_id = %s",
                (case_id, firm_id),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Claim not found")
            stage = row["claim_stage"]

        _ensure_checklist(conn, firm_id, case_id, stage)
        conn.commit()

        rows = conn.execute(
            """
            SELECT id, stage, item_key, label, status, note, updated_at
            FROM claim_checklists
            WHERE case_id = %s AND firm_id = %s AND stage = %s
            ORDER BY id
            """,
            (case_id, firm_id, stage),
        ).fetchall()
    return {"success": True, "stage": stage, "items": [dict(r) for r in rows]}


@router.post("/vcf/cases/{case_id}/checklist/{item_id}")
async def update_checklist_item(case_id: int, item_id: int, body: ChecklistItemUpdate, request: Request):
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    if body.status not in {"pending", "complete", "not_applicable"}:
        raise HTTPException(400, "status must be pending, complete, or not_applicable")

    with get_conn(firm_id) as conn:
        row = conn.execute(
            """
            UPDATE claim_checklists
            SET status = %s, note = COALESCE(%s, note), updated_at = NOW()
            WHERE id = %s AND case_id = %s AND firm_id = %s
            RETURNING id, stage, item_key, label, status
            """,
            (body.status, body.note, item_id, case_id, firm_id),
        ).fetchone()
        conn.commit()
        if not row:
            raise HTTPException(404, "Checklist item not found")
    return {"success": True, "item": dict(row)}


@router.get("/vcf/stages")
async def list_stages():
    return {"success": True, "stages": CLAIM_STAGES}
