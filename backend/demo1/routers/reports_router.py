from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import sqlite3, os, json

router = APIRouter(prefix="/reports", tags=["reports"])

DB_PATH = os.environ.get("DB_PATH", "/root/nlp-portfolio/analyses.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id INTEGER,
            firm_id INTEGER,
            report_type TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'generating',
            content TEXT,
            metadata TEXT,
            generated_by TEXT DEFAULT 'manual',
            created_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_table()

REPORT_TYPES = [
    "case_summary", "timeline_report", "privilege_log", "discovery_index",
    "contradiction_report", "deadline_report", "correspondence_log",
    "contact_sheet", "research_memo", "custom"
]

class ReportCreate(BaseModel):
    matter_id: Optional[int] = None
    firm_id: Optional[int] = None
    report_type: str
    title: str
    content: Optional[str] = ""
    metadata: Optional[dict] = None
    generated_by: Optional[str] = "manual"
    created_by: Optional[str] = ""

class ReportUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None

def _build_report_content(matter_id: int, report_type: str, conn) -> str:
    """Assemble report content from existing DB data."""
    if report_type == "case_summary":
        case = conn.execute("SELECT * FROM cases WHERE id = ?", (matter_id,)).fetchone()
        if not case:
            return "Case not found."
        docs = conn.execute("SELECT COUNT(*) as c FROM documents WHERE case_id = ?", (matter_id,)).fetchone()
        return json.dumps({
            "case": dict(case),
            "document_count": docs["c"] if docs else 0,
            "generated_at": datetime.now().isoformat()
        }, indent=2)
    elif report_type == "deadline_report":
        rows = conn.execute(
            "SELECT * FROM calendar_events WHERE matter_id = ? ORDER BY due_date ASC", (matter_id,)
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)
    elif report_type == "privilege_log":
        rows = conn.execute(
            "SELECT * FROM privilege_log WHERE matter_id = ? ORDER BY created_at DESC",
            (matter_id,)
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)
    elif report_type == "discovery_index":
        rows = conn.execute(
            "SELECT * FROM documents WHERE case_id = ? ORDER BY created_at DESC", (matter_id,)
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)
    elif report_type == "correspondence_log":
        rows = conn.execute(
            "SELECT * FROM correspondence WHERE matter_id = ? ORDER BY date DESC", (matter_id,)
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)
    elif report_type == "contact_sheet":
        rows = conn.execute(
            "SELECT * FROM contacts WHERE matter_id = ? ORDER BY name ASC", (matter_id,)
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)
    elif report_type == "contradiction_report":
        rows = conn.execute(
            "SELECT * FROM case_contradictions WHERE case_id = ? ORDER BY severity DESC", (matter_id,)
        ).fetchall()
        return json.dumps([dict(r) for r in rows], indent=2)
    return ""

@router.get("/matter/{matter_id}")
def list_matter_reports(matter_id: int, report_type: Optional[str] = None):
    conn = get_db()
    q = "SELECT id, matter_id, firm_id, report_type, title, status, generated_by, created_by, created_at FROM reports WHERE matter_id = ?"
    params = [matter_id]
    if report_type:
        q += " AND report_type = ?"
        params.append(report_type)
    q += " ORDER BY created_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/{report_id}")
def get_report(report_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)

@router.post("/generate/{matter_id}/{report_type}")
def generate_report(matter_id: int, report_type: str, created_by: Optional[str] = ""):
    if report_type not in REPORT_TYPES:
        raise HTTPException(400, f"Invalid report type. Valid: {REPORT_TYPES}")
    conn = get_db()
    title = f"{report_type.replace('_', ' ').title()} — Matter #{matter_id}"
    content = _build_report_content(matter_id, report_type, conn)
    cur = conn.execute("""
        INSERT INTO reports (matter_id, report_type, title, status, content, generated_by, created_by)
        VALUES (?, ?, ?, 'complete', ?, 'system', ?)
    """, (matter_id, report_type, title, content, created_by))
    conn.commit()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)

@router.post("/")
def create_manual_report(report: ReportCreate):
    conn = get_db()
    meta = json.dumps(report.metadata) if report.metadata else None
    cur = conn.execute("""
        INSERT INTO reports (matter_id, firm_id, report_type, title, status, content, metadata, generated_by, created_by)
        VALUES (?, ?, ?, ?, 'complete', ?, ?, ?, ?)
    """, (report.matter_id, report.firm_id, report.report_type, report.title,
          report.content, meta, report.generated_by, report.created_by))
    conn.commit()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)

@router.delete("/{report_id}")
def delete_report(report_id: int):
    conn = get_db()
    conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()
    return {"deleted": report_id}

@router.get("/types/list")
def get_report_types():
    return {"types": REPORT_TYPES}
