import sqlite3, csv, io, os, json
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import anthropic

router = APIRouter(prefix="/privilege", tags=["Privilege Log"])

DB_PATH = "/root/nlp-portfolio/backend/demo1/analyses.db"
def get_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_privilege_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS privilege_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            case_number    TEXT NOT NULL,
            doc_id         INTEGER,
            filename       TEXT NOT NULL,
            doc_date       TEXT,
            author         TEXT,
            recipients     TEXT,
            privilege_type TEXT NOT NULL,
            basis          TEXT NOT NULL,
            withheld_at    TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_privilege_table()

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

def generate_privilege_entry(filename: str, doc_date: str, case_number: str) -> dict:
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
        msg = get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        raw = raw.replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except Exception:
        return {
            "author":         "Unknown",
            "recipients":     "Unknown",
            "privilege_type": "Attorney-Client Privilege",
            "basis":          "Document withheld as potentially privileged pending review."
        }

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/log/generate")
def generate_log(body: GenerateLogIn):
    """Use Claude to auto-populate privilege log entries for selected files."""
    conn = get_conn()
    ph   = ",".join("?" * len(body.file_ids))
    rows = conn.execute(
        f"SELECT * FROM discovery_files WHERE id IN ({ph})", body.file_ids
    ).fetchall()
    conn.close()

    if not rows:
        raise HTTPException(404, "No files found for given IDs")

    generated = []
    for row in rows:
        entry = generate_privilege_entry(
            row["original_name"], row["doc_date"], body.case_number
        )
        conn = get_conn()
        cur  = conn.execute("""
            INSERT INTO privilege_log
              (case_number, doc_id, filename, doc_date, author, recipients,
               privilege_type, basis)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            body.case_number, row["id"], row["original_name"],
            row["doc_date"],  entry["author"], entry["recipients"],
            entry["privilege_type"], entry["basis"]
        ))
        log_id = cur.lastrowid
        conn.execute(
            "UPDATE discovery_files SET status='withheld' WHERE id=?", (row["id"],)
        )
        conn.commit()
        conn.close()

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
        "success":   True,
        "case_number": body.case_number,
        "generated": len(generated),
        "entries":   generated,
    }

@router.post("/log/entry")
def add_manual_entry(body: ManualEntryIn):
    """Manually add a privilege log entry."""
    conn = get_conn()
    cur  = conn.execute("""
        INSERT INTO privilege_log
          (case_number, doc_id, filename, doc_date, author, recipients,
           privilege_type, basis)
        VALUES (?,?,?,?,?,?,?,?)
    """, (body.case_number, body.doc_id, body.filename, body.doc_date,
          body.author, body.recipients, body.privilege_type, body.basis))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "id": log_id}

@router.get("/log/{case_number}")
def get_log(case_number: str):
    """Get the full privilege log for a case."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM privilege_log WHERE case_number=? ORDER BY id ASC",
        (case_number,)
    ).fetchall()
    conn.close()
    return {
        "case_number": case_number,
        "total":       len(rows),
        "entries":     [dict(r) for r in rows],
    }

@router.get("/log/{case_number}/export")
def export_log(case_number: str):
    """Export privilege log as CSV."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM privilege_log WHERE case_number=? ORDER BY id ASC",
        (case_number,)
    ).fetchall()
    conn.close()

    if not rows:
        raise HTTPException(404, f"No privilege log entries for case '{case_number}'")

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["#","Document","Date","Author","Recipients",
                "Privilege Type","Basis for Withholding","Logged At"])
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
def delete_entry(entry_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM privilege_log WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()
    return {"success": True}


# ── Feature 25: Privilege Flagging AI ────────────────────────────────────────

class FlagTextIn(BaseModel):
    text:        str
    case_number: Optional[str] = None

@router.post("/flag")
def flag_privilege(body: FlagTextIn):
    """Analyze document text clause-by-clause for privilege markers."""
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
        msg = get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip().replace("```json","").replace("```","").strip()
        result = json.loads(raw)
        result["case_number"] = body.case_number
        return {"success": True, **result}
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"JSON parse error: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/log")
def list_all_privilege_entries(
    limit:          int  = 100,
    offset:         int  = 0,
    case_number:    str  = None,
    privilege_type: str  = None,
    only_flagged:   bool = False,
):
    """General listing of all privilege log entries across all cases."""
    conn  = get_conn()
    where = []
    args  = []
    if case_number:
        where.append("case_number = ?")
        args.append(case_number)
    if privilege_type:
        where.append("privilege_type = ?")
        args.append(privilege_type)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(
        f"SELECT COUNT(*) FROM privilege_log {where_sql}", args
    ).fetchone()[0]
    rows = conn.execute(
        f"""SELECT id, case_number, doc_id, filename, doc_date,
                   author, recipients, privilege_type, basis, withheld_at
            FROM privilege_log {where_sql}
            ORDER BY withheld_at DESC LIMIT ? OFFSET ?""",
        args + [limit, offset]
    ).fetchall()
    conn.close()
    return {
        "success": True,
        "total":   total,
        "offset":  offset,
        "limit":   limit,
        "entries": [dict(r) for r in rows],
    }


@router.get("/stats")
def privilege_stats():
    """Summary stats for the privilege log dashboard."""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM privilege_log").fetchone()[0]
    by_type = conn.execute(
        "SELECT privilege_type, COUNT(*) as count FROM privilege_log GROUP BY privilege_type"
    ).fetchall()
    by_case = conn.execute(
        "SELECT case_number, COUNT(*) as count FROM privilege_log GROUP BY case_number ORDER BY count DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return {
        "success":  True,
        "total":    total,
        "by_type":  [dict(r) for r in by_type],
        "by_case":  [dict(r) for r in by_case],
    }
