from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import sqlite3, os

router = APIRouter(prefix="/correspondence", tags=["correspondence"])

DB_PATH = os.environ.get("DB_PATH", "/root/nlp-portfolio/analyses.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS correspondence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id INTEGER NOT NULL,
            firm_id INTEGER,
            type TEXT DEFAULT 'email',
            direction TEXT DEFAULT 'outbound',
            subject TEXT NOT NULL,
            body TEXT,
            from_party TEXT,
            to_party TEXT,
            cc_party TEXT,
            date TEXT,
            status TEXT DEFAULT 'draft',
            attachments TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_table()

class CorrespondenceCreate(BaseModel):
    matter_id: int
    firm_id: Optional[int] = None
    type: Optional[str] = "email"
    direction: Optional[str] = "outbound"
    subject: str
    body: Optional[str] = ""
    from_party: Optional[str] = ""
    to_party: Optional[str] = ""
    cc_party: Optional[str] = ""
    date: Optional[str] = None
    status: Optional[str] = "draft"
    attachments: Optional[str] = ""

class CorrespondenceUpdate(BaseModel):
    type: Optional[str] = None
    direction: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    from_party: Optional[str] = None
    to_party: Optional[str] = None
    cc_party: Optional[str] = None
    date: Optional[str] = None
    status: Optional[str] = None
    attachments: Optional[str] = None

@router.get("/{matter_id}")
def list_correspondence(matter_id: int, type: Optional[str] = None, direction: Optional[str] = None):
    conn = get_db()
    query = "SELECT * FROM correspondence WHERE matter_id = ?"
    params = [matter_id]
    if type:
        query += " AND type = ?"
        params.append(type)
    if direction:
        query += " AND direction = ?"
        params.append(direction)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/")
def create_correspondence(item: CorrespondenceCreate):
    conn = get_db()
    date_val = item.date or datetime.now().strftime("%Y-%m-%d")
    cur = conn.execute("""
        INSERT INTO correspondence (matter_id, firm_id, type, direction, subject, body,
            from_party, to_party, cc_party, date, status, attachments)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (item.matter_id, item.firm_id, item.type, item.direction, item.subject,
          item.body, item.from_party, item.to_party, item.cc_party,
          date_val, item.status, item.attachments))
    conn.commit()
    row = conn.execute("SELECT * FROM correspondence WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)

@router.put("/{item_id}")
def update_correspondence(item_id: int, item: CorrespondenceUpdate):
    conn = get_db()
    fields = {k: v for k, v in item.dict().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE correspondence SET {set_clause} WHERE id = ?",
                 list(fields.values()) + [item_id])
    conn.commit()
    row = conn.execute("SELECT * FROM correspondence WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)

@router.delete("/{item_id}")
def delete_correspondence(item_id: int):
    conn = get_db()
    conn.execute("DELETE FROM correspondence WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"deleted": item_id}
