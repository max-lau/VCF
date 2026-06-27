"""
drafting_router.py  —  AI Drafting Assistant
=============================================
Mount in main.py:
    from backend.demo1.drafting_router import router as drafting_router
    app.include_router(drafting_router, prefix="/draft", tags=["drafting"])
"""

import os, json, logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.demo1.auth import get_current_user, get_current_firm_id
from backend.demo1.pg import get_conn
from backend.demo1.ai_client import get_client

router = APIRouter()
log    = logging.getLogger(__name__)
_ai    = get_client()

# ── Request models ────────────────────────────────────────────────────────────

class DraftRequest(BaseModel):
    instructions: Optional[str] = ""   # optional free-text from lawyer

# ── Shared context builder ────────────────────────────────────────────────────

def _build_case_context(case_id: int, firm_id: str) -> dict:
    with get_conn(firm_id) as conn:
        case = conn.execute(
            "SELECT * FROM cases WHERE id=%s", (case_id,)
        ).fetchone()
        if not case:
            raise HTTPException(404, "Case not found")
        case = dict(case)

        docs = conn.execute(
            """SELECT document_name, summary, doc_text, events_json
               FROM case_documents WHERE case_id=%s ORDER BY upload_date ASC LIMIT 8""",
            (case_id,)
        ).fetchall()
        docs = [dict(d) for d in docs]

        notes = conn.execute(
            "SELECT note, author FROM case_notes WHERE case_id=%s ORDER BY created_at DESC LIMIT 5",
            (case_id,)
        ).fetchall()
        notes = [dict(n) for n in notes]

    doc_blocks, all_events = [], []
    for d in docs:
        snippet = d.get("summary") or (d.get("doc_text") or "")[:300]
        doc_blocks.append(f"• {d['document_name']}: {snippet}")
        if d.get("events_json"):
            try:
                evs = d["events_json"] if isinstance(d["events_json"], list) else json.loads(d["events_json"])
                all_events.extend(evs[:3])
            except (json.JSONDecodeError, KeyError, TypeError): pass

    return {
        "case":       case,
        "doc_blocks": "\n".join(doc_blocks[:6]) or "No documents uploaded yet.",
        "events":     json.dumps(all_events[:6], indent=2) if all_events else "None extracted.",
        "notes":      "\n".join(f"[{n['author']}] {n['note']}" for n in notes) or "None.",
        "today":      datetime.now().strftime("%B %d, %Y"),
    }

def _call_claude(prompt: str, max_tokens: int = 2000) -> str:
    msg = _ai.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()

# ── 1. Case Brief ─────────────────────────────────────────────────────────────

@router.post("/brief/{case_id}")
def draft_brief(
    case_id: int,
    body: DraftRequest,
    user=Depends(get_current_user),
    firm_id: str = Depends(get_current_firm_id),
):
    ctx = _build_case_context(case_id, firm_id)
    c   = ctx["case"]
    prompt = f"""You are a senior litigation paralegal at a U.S. law firm.
Draft a structured case brief for attorney review.

CASE: {c['case_number']} — {c['client_name']}
Court: {c.get('court') or 'TBD'} | Judge: {c.get('judge') or 'TBD'}
Filing Date: {c.get('filing_date') or 'TBD'} | Status: {c.get('status','open')}
Matter: {c.get('description') or 'Not specified'}

DOCUMENTS:
{ctx['doc_blocks']}

KEY EVENTS:
{ctx['events']}

COUNSEL NOTES:
{ctx['notes']}

ADDITIONAL INSTRUCTIONS: {body.instructions or 'None.'}

Write a professional 2-page case brief with these sections:
I. PARTIES AND BACKGROUND
II. STATEMENT OF FACTS
III. LEGAL ISSUES PRESENTED
IV. KEY EVIDENCE SUMMARY
V. RISK ASSESSMENT
VI. RECOMMENDED NEXT STEPS
VII. CRITICAL DEADLINES

Use formal legal memo style. Date: {ctx['today']}"""

    text = _call_claude(prompt, 2500)
    return {"doc_type": "brief", "case_id": case_id, "content": text,
            "generated_at": ctx["today"], "case_number": c["case_number"],
            "matter": c["client_name"]}

# ── 2. Motion Draft ───────────────────────────────────────────────────────────

class MotionRequest(DraftRequest):
    motion_type: str = "motion_to_dismiss"  # motion_to_dismiss | motion_to_compel | msj | motion_in_limine

MOTION_LABELS = {
    "motion_to_dismiss":  "Motion to Dismiss",
    "motion_to_compel":   "Motion to Compel",
    "msj":                "Motion for Summary Judgment",
    "motion_in_limine":   "Motion in Limine",
}

@router.post("/motion/{case_id}")
def draft_motion(
    case_id: int,
    body: MotionRequest,
    user=Depends(get_current_user),
    firm_id: str = Depends(get_current_firm_id),
):
    ctx   = _build_case_context(case_id, firm_id)
    c     = ctx["case"]
    label = MOTION_LABELS.get(body.motion_type, "Motion")
    prompt = f"""You are a litigation attorney drafting a {label} for filing in {c.get('court') or 'federal court'}.

CASE: {c['case_number']} — {c['client_name']}
Court: {c.get('court') or 'TBD'} | Judge: {c.get('judge') or 'TBD'}
Filing Date: {c.get('filing_date') or 'TBD'}

CASE DOCUMENTS SUMMARY:
{ctx['doc_blocks']}

KEY EVENTS:
{ctx['events']}

ATTORNEY INSTRUCTIONS: {body.instructions or 'Draft a complete motion with standard structure.'}

Draft a complete {label} including:
- Caption (case name, court, case number)
- Introduction / Preliminary Statement
- Statement of Facts
- Legal Standard
- Argument (with numbered subsections)
- Conclusion and Relief Requested
- Certificate of Service placeholder

Use proper legal formatting. Date: {ctx['today']}"""

    text = _call_claude(prompt, 3000)
    return {"doc_type": "motion", "motion_type": body.motion_type,
            "motion_label": label, "case_id": case_id, "content": text,
            "generated_at": ctx["today"], "case_number": c["case_number"],
            "matter": c["client_name"]}

# ── 3. Client Letter ──────────────────────────────────────────────────────────

@router.post("/letter/{case_id}")
def draft_letter(
    case_id: int,
    body: DraftRequest,
    user=Depends(get_current_user),
    firm_id: str = Depends(get_current_firm_id),
):
    ctx = _build_case_context(case_id, firm_id)
    c   = ctx["case"]
    prompt = f"""You are a litigation attorney writing a status update letter to your client.

CASE: {c['case_number']} — {c['client_name']}
Court: {c.get('court') or 'TBD'} | Status: {c.get('status','open')}
Matter: {c.get('description') or 'Not specified'}

RECENT ACTIVITY:
{ctx['doc_blocks']}

KEY EVENTS:
{ctx['events']}

ATTORNEY INSTRUCTIONS: {body.instructions or 'Write a professional client status update letter.'}

Write a formal client status update letter including:
- Firm letterhead placeholder
- Date: {ctx['today']}
- Client greeting (Dear [Client Name],)
- Current case status summary
- Recent developments
- Next steps and what to expect
- Any action items required from client
- Professional closing

Keep the tone professional but accessible — avoid excessive legal jargon."""

    text = _call_claude(prompt, 1500)
    return {"doc_type": "letter", "case_id": case_id, "content": text,
            "generated_at": ctx["today"], "case_number": c["case_number"],
            "matter": c["client_name"]}

# ── 4. Demand Letter ──────────────────────────────────────────────────────────

@router.post("/demand/{case_id}")
def draft_demand(
    case_id: int,
    body: DraftRequest,
    user=Depends(get_current_user),
    firm_id: str = Depends(get_current_firm_id),
):
    ctx = _build_case_context(case_id, firm_id)
    c   = ctx["case"]
    prompt = f"""You are a litigation attorney drafting a formal demand letter on behalf of your client.

CASE: {c['case_number']} — {c['client_name']}
Court: {c.get('court') or 'TBD'} | Matter: {c.get('description') or 'Not specified'}

SUPPORTING DOCUMENTS:
{ctx['doc_blocks']}

KEY EVENTS:
{ctx['events']}

ATTORNEY INSTRUCTIONS: {body.instructions or 'Draft a firm but professional demand letter.'}

Draft a formal demand letter including:
- Firm letterhead placeholder
- Date: {ctx['today']}
- Re: line with case reference
- Opening statement of representation
- Statement of facts and liability
- Damages claimed (use facts from documents)
- Specific demand and deadline for response (typically 30 days)
- Consequences of non-response
- Professional closing with attorney signature block placeholder

Tone should be firm, professional, and unambiguous."""

    text = _call_claude(prompt, 1500)
    return {"doc_type": "demand", "case_id": case_id, "content": text,
            "generated_at": ctx["today"], "case_number": c["case_number"],
            "matter": c["client_name"]}

# ── 5. List saved drafts ──────────────────────────────────────────────────────

@router.get("/drafts/{case_id}")
def list_drafts(
    case_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """SELECT id, doc_type, doc_label, created_at
               FROM ai_drafts
               WHERE case_id=%s AND firm_id=%s
               ORDER BY created_at DESC""",
            (case_id, firm_id)
        ).fetchall()
    return {"drafts": [dict(r) for r in rows]}

@router.post("/save/{case_id}")
def save_draft(
    case_id: int,
    body: dict,
    user=Depends(get_current_user),
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        cur = conn.execute(
            """INSERT INTO ai_drafts (case_id, firm_id, doc_type, doc_label, content, created_by)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (case_id, firm_id,
             body.get("doc_type"), body.get("doc_label"),
             body.get("content"), user.get("username"))
        )
        row = cur.fetchone()
    return {"ok": True, "id": row["id"]}
