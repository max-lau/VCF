from pathlib import Path
import os
import csv, io, json
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/privilege", tags=["Privilege Log"])


def init_privilege_table():
    """No-op — table exists in Supabase Postgres."""
    print("[Privilege] DB table initialized [OK]")


# ── Models ────────────────────────────────────────────────────────────────────

class GenerateLogIn(BaseModel):
    case_number: str
    file_ids:    List[int]

class ManualEntryIn(BaseModel):
    case_number:    str
    doc_id:         Optional[int] = None
    filename:       str
    doc_date:       Optional[str] = None
    author:         Optional[str] = None
    recipients:     Optional[str] = None
    privilege_type: str
    basis:          str

# ── Claude helper ─────────────────────────────────────────────────────────────

def generate_privilege_entry(filename: str, doc_date: str, case_number: str,
                              firm_id: str = "default") -> dict:
    from backend.demo1.main import claude_with_retry, client, LLM_FAST, clean_json
    prompt = f"""You are a litigation paralegal generating a privilege log entry.
Given only the document filename and date, infer the most likely privilege basis.

Document: {filename}
Date: {doc_date or "unknown"}
Case: {case_number}

Return ONLY valid JSON, no markdown:
{{
  "author": "inferred author or role (e.g. 'Outside Counsel', 'Client', 'Unknown')",
  "recipients": "inferred recipients (e.g. 'Legal Team', 'Client', 'Unknown')",
  "privilege_type": "one of: Attorney-Client Privilege | Work Product Doctrine | Both | Common Interest Privilege",
  "basis": "one sentence legal basis for withholding (cite Upjohn or relevant doctrine if applicable)"
}}"""

    try:
        msg = claude_with_retry(
            client.messages.create,
            model=LLM_FAST,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
            firm_id=firm_id,
        )
        raw = msg.content[0].text.strip()
        raw = clean_json(raw)
        return json.loads(raw)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.warning(f"[PrivilegeLog] LLM/JSON parse failed for {filename}: {e}")
        return {
            "author":         "Unknown",
            "recipients":     "Unknown",
            "privilege_type": "Attorney-Client Privilege",
            "basis":          "Document withheld as potentially privileged pending review."
        }

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/log/generate")
def generate_log(body: GenerateLogIn, request: Request):
    """Use Claude to auto-populate privilege log entries for selected files."""
    firm_id = getattr(request.state, "firm_id", "default")
    ph = ",".join(["%s"] * len(body.file_ids))
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            f"SELECT * FROM discovery_files WHERE id IN ({ph}) AND firm_id=%s",
            body.file_ids + [firm_id]
        ).fetchall()

    if not rows:
        raise HTTPException(404, "No files found for given IDs")

    generated = []
    for row in rows:
        entry = generate_privilege_entry(
            row["original_name"], row["doc_date"], body.case_number, firm_id
        )
        with get_conn(firm_id) as conn:
            cur = conn.execute("""
                INSERT INTO privilege_log
                  (case_number, doc_id, filename, doc_date, author, recipients,
                   privilege_type, basis, firm_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                body.case_number, row["id"], row["original_name"],
                row["doc_date"], entry["author"], entry["recipients"],
                entry["privilege_type"], entry["basis"], firm_id
            ))
            log_id = cur.fetchone()["id"]
            conn.execute(
                "UPDATE discovery_files SET status='withheld' WHERE id=%s AND firm_id=%s",
                (row["id"], firm_id)
            )

        generated.append({
            "id":             log_id,
            "doc_id":         row["id"],
            "filename":       row["original_name"],
            "doc_date":       row["doc_date"],
            "author":         entry["author"],
            "recipients":     entry["recipients"],
            "privilege_type": entry["privilege_type"],
            "basis":          entry["basis"],
        })

    return {
        "success":     True,
        "case_number": body.case_number,
        "generated":   len(generated),
        "entries":     generated,
    }


@router.post("/log/entry")
def add_manual_entry(body: ManualEntryIn, request: Request):
    """Manually add a privilege log entry."""
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO privilege_log
              (case_number, doc_id, filename, doc_date, author, recipients,
               privilege_type, basis, firm_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (body.case_number, body.doc_id, body.filename, body.doc_date,
              body.author, body.recipients, body.privilege_type, body.basis, firm_id))
        log_id = cur.fetchone()["id"]
    return {"success": True, "id": log_id}


@router.get("/log/{case_number}")
def get_log(case_number: str, request: Request):
    """Get the full privilege log for a case."""
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT * FROM privilege_log WHERE case_number=%s AND firm_id=%s ORDER BY id ASC",
            (case_number, firm_id)
        ).fetchall()
    return {
        "case_number": case_number,
        "total":       len(rows),
        "entries":     [dict(r) for r in rows],
    }


@router.get("/log/{case_number}/export")
def export_log(case_number: str, request: Request):
    """Export privilege log as CSV."""
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT * FROM privilege_log WHERE case_number=%s AND firm_id=%s ORDER BY id ASC",
            (case_number, firm_id)
        ).fetchall()

    if not rows:
        raise HTTPException(404, f"No privilege log entries for case '{case_number}'")

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["#", "Document", "Date", "Author", "Recipients",
                "Privilege Type", "Basis for Withholding", "Logged At"])
    for i, r in enumerate(rows, 1):
        w.writerow([i, r["filename"], r["doc_date"] or "",
                    r["author"] or "", r["recipients"] or "",
                    r["privilege_type"], r["basis"], r["withheld_at"]])

    buf.seek(0)
    fname = f"Privilege_Log_{case_number}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )


@router.delete("/log/entry/{entry_id}")
def delete_entry(entry_id: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT id FROM privilege_log WHERE id=%s AND firm_id=%s",
            (entry_id, firm_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Entry not found")
        conn.execute(
            "DELETE FROM privilege_log WHERE id=%s AND firm_id=%s",
            (entry_id, firm_id)
        )
    return {"success": True}


# ── Privilege Flagging AI ─────────────────────────────────────────────────────

class FlagTextIn(BaseModel):
    text:        str
    case_number: Optional[str] = None

@router.post("/flag")
def flag_privilege(body: FlagTextIn, request: Request):
    """Analyze document text clause-by-clause for privilege markers."""
    from backend.demo1.main import claude_with_retry, client, LLM_FAST, clean_json
    firm_id = getattr(request.state, "firm_id", "default")
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(400, "Text too short")

    prompt = f"""You are a legal privilege analyst. Analyze the following document text and identify every clause or sentence that may be protected by attorney-client privilege or work product doctrine.

Return ONLY valid JSON, no markdown:
{{
  "overall_risk": "high|medium|low|none",
  "summary": "one sentence overall assessment",
  "flagged_clauses": [
    {{
      "text": "exact clause or sentence from document",
      "privilege_type": "Attorney-Client Privilege|Work Product Doctrine|Both|Common Interest|None",
      "confidence": "high|medium|low",
      "reason": "one sentence explanation of why this is privileged",
      "recommendation": "Withhold|Redact|Produce with caution|Produce"
    }}
  ],
  "total_flagged": 0,
  "withhold_count": 0,
  "redact_count": 0
}}

Document text:
{body.text[:6000]}"""

    try:
        msg = claude_with_retry(
            client.messages.create,
            model=LLM_FAST,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
            firm_id=firm_id,
        )
        raw = msg.content[0].text.strip()
        raw = clean_json(raw)
        result = json.loads(raw)
        result["case_number"] = body.case_number
        return {"success": True, **result}
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"JSON parse error: {e}")
    except Exception as e:
        raise HTTPException(500, "Privilege analysis failed")


@router.get("/log")
def list_all_privilege_entries(
    request:        Request,
    limit:          int  = 100,
    offset:         int  = 0,
    case_number:    str  = None,
    privilege_type: str  = None,
):
    """List privilege log entries scoped to current firm."""
    firm_id = getattr(request.state, "firm_id", "default")
    where = ["firm_id = %s"]
    args  = [firm_id]
    if case_number:
        where.append("case_number = %s")
        args.append(case_number)
    if privilege_type:
        where.append("privilege_type = %s")
        args.append(privilege_type)
    where_sql = "WHERE " + " AND ".join(where)
    with get_conn(firm_id) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) as c FROM privilege_log {where_sql}", args
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT id, case_number, doc_id, filename, doc_date,
                       author, recipients, privilege_type, basis, withheld_at
                FROM privilege_log {where_sql}
                ORDER BY withheld_at DESC LIMIT %s OFFSET %s""",
            args + [limit, offset]
        ).fetchall()
    return {
        "success": True,
        "total":   total,
        "offset":  offset,
        "limit":   limit,
        "entries": [dict(r) for r in rows],
    }


@router.get("/stats")
def privilege_stats(request: Request):
    """Summary stats for the privilege log dashboard."""
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        total = conn.execute(
            "SELECT COUNT(*) as c FROM privilege_log WHERE firm_id=%s", (firm_id,)
        ).fetchone()["c"]
        by_type = conn.execute(
            "SELECT privilege_type, COUNT(*) as count FROM privilege_log WHERE firm_id=%s GROUP BY privilege_type",
            (firm_id,)
        ).fetchall()
        by_case = conn.execute(
            "SELECT case_number, COUNT(*) as count FROM privilege_log WHERE firm_id=%s GROUP BY case_number ORDER BY count DESC LIMIT 10",
            (firm_id,)
        ).fetchall()
    return {
        "success": True,
        "total":   total,
        "by_type": [dict(r) for r in by_type],
        "by_case": [dict(r) for r in by_case],
    }
