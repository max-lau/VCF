from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.demo1.auth import get_current_firm_id, get_current_user
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import sqlite3, os

router = APIRouter(prefix="/research", tags=["research"])

DB_PATH = os.environ.get("DB_PATH", "/root/nlp-portfolio/analyses.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id INTEGER,
            firm_id INTEGER,
            title TEXT NOT NULL,
            research_type TEXT DEFAULT 'case_law',
            citation TEXT,
            jurisdiction TEXT,
            summary TEXT,
            body TEXT,
            relevance TEXT,
            url TEXT,
            tags TEXT,
            is_favorable INTEGER DEFAULT 1,
            created_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_table()

RESEARCH_TYPES = ["case_law", "statute", "regulation", "secondary", "memo", "brief", "other"]

class ResearchCreate(BaseModel):
    matter_id: Optional[int] = None
    firm_id: Optional[int] = None
    title: str
    research_type: Optional[str] = "case_law"
    citation: Optional[str] = ""
    jurisdiction: Optional[str] = ""
    summary: Optional[str] = ""
    body: Optional[str] = ""
    relevance: Optional[str] = ""
    url: Optional[str] = ""
    tags: Optional[str] = ""
    is_favorable: Optional[bool] = True
    created_by: Optional[str] = ""

class ResearchUpdate(BaseModel):
    title: Optional[str] = None
    research_type: Optional[str] = None
    citation: Optional[str] = None
    jurisdiction: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    relevance: Optional[str] = None
    url: Optional[str] = None
    tags: Optional[str] = None
    is_favorable: Optional[bool] = None

@router.get("/matter/{matter_id}")
def list_matter_research(matter_id: int, research_type: Optional[str] = None, is_favorable: Optional[bool] = None, _auth: str = Depends(get_current_firm_id)):
    conn = get_db()
    q = "SELECT * FROM research_notes WHERE matter_id = ?"
    params = [matter_id]
    if research_type:
        q += " AND research_type = ?"
        params.append(research_type)
    if is_favorable is not None:
        q += " AND is_favorable = ?"
        params.append(int(is_favorable))
    q += " ORDER BY created_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/firm/{firm_id}")
def list_firm_research(firm_id: int, search: Optional[str] = None, _auth: str = Depends(get_current_firm_id)):
    conn = get_db()
    q = "SELECT * FROM research_notes WHERE firm_id = ?"
    params = [firm_id]
    if search:
        q += " AND (title LIKE ? OR citation LIKE ? OR summary LIKE ? OR tags LIKE ?)"
        s = f"%{search}%"
        params += [s, s, s, s]
    q += " ORDER BY created_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/{note_id}")
def get_research_note(note_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM research_notes WHERE id = ?", (note_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)

@router.post("/")
def create_research_note(note: ResearchCreate, _auth: str = Depends(get_current_firm_id)):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO research_notes (matter_id, firm_id, title, research_type, citation, jurisdiction,
            summary, body, relevance, url, tags, is_favorable, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (note.matter_id, note.firm_id, note.title, note.research_type, note.citation,
          note.jurisdiction, note.summary, note.body, note.relevance, note.url,
          note.tags, int(note.is_favorable or 1), note.created_by))
    conn.commit()
    row = conn.execute("SELECT * FROM research_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)

@router.put("/{note_id}")
def update_research_note(note_id: int, note: ResearchUpdate, _auth: str = Depends(get_current_firm_id)):
    conn = get_db()
    fields = {k: v for k, v in note.dict().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    if "is_favorable" in fields:
        fields["is_favorable"] = int(fields["is_favorable"])
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE research_notes SET {set_clause} WHERE id = ?",
                 list(fields.values()) + [note_id])
    conn.commit()
    row = conn.execute("SELECT * FROM research_notes WHERE id = ?", (note_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)

@router.delete("/{note_id}")
def delete_research_note(note_id: int, _auth: str = Depends(get_current_firm_id)):
    conn = get_db()
    conn.execute("DELETE FROM research_notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    return {"deleted": note_id}

@router.get("/types/list")
def get_research_types():
    return {"types": RESEARCH_TYPES}
