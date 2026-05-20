from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import sqlite3, os

router = APIRouter(prefix="/calendar", tags=["calendar"])

DB_PATH = os.environ.get("DB_PATH", "/root/nlp-portfolio/analyses.db")

EVENT_TYPES = ["deadline", "hearing", "deposition", "meeting", "filing", "trial", "conference", "other"]
STATUSES    = ["upcoming", "completed", "cancelled", "rescheduled"]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id INTEGER,
            firm_id INTEGER,
            title TEXT NOT NULL,
            event_type TEXT DEFAULT 'deadline',
            due_date TEXT NOT NULL,
            due_time TEXT,
            location TEXT,
            description TEXT,
            attendees TEXT,
            status TEXT DEFAULT 'upcoming',
            reminder_days INTEGER DEFAULT 3,
            is_court_date INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_table()

class EventCreate(BaseModel):
    matter_id: Optional[int] = None
    firm_id: Optional[int] = None
    title: str
    event_type: Optional[str] = "deadline"
    due_date: str
    due_time: Optional[str] = None
    location: Optional[str] = ""
    description: Optional[str] = ""
    attendees: Optional[str] = ""
    status: Optional[str] = "upcoming"
    reminder_days: Optional[int] = 3
    is_court_date: Optional[bool] = False

class EventUpdate(BaseModel):
    title: Optional[str] = None
    event_type: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    attendees: Optional[str] = None
    status: Optional[str] = None
    reminder_days: Optional[int] = None
    is_court_date: Optional[bool] = None

@router.get("/matter/{matter_id}")
def list_matter_events(matter_id: int, status: Optional[str] = None):
    conn = get_db()
    q = "SELECT * FROM calendar_events WHERE matter_id = ?"
    params = [matter_id]
    if status:
        q += " AND status = ?"
        params.append(status)
    q += " ORDER BY due_date ASC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/firm/{firm_id}")
def list_firm_events(firm_id: int, days_ahead: int = 30, status: Optional[str] = None):
    conn = get_db()
    cutoff = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    today   = datetime.now().strftime("%Y-%m-%d")
    q = "SELECT * FROM calendar_events WHERE firm_id = ? AND due_date BETWEEN ? AND ?"
    params = [firm_id, today, cutoff]
    if status:
        q += " AND status = ?"
        params.append(status)
    q += " ORDER BY due_date ASC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/upcoming")
def upcoming_events(days_ahead: int = 7, firm_id: Optional[int] = None):
    conn = get_db()
    cutoff = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    today   = datetime.now().strftime("%Y-%m-%d")
    q = "SELECT * FROM calendar_events WHERE due_date BETWEEN ? AND ? AND status = 'upcoming'"
    params = [today, cutoff]
    if firm_id:
        q += " AND firm_id = ?"
        params.append(firm_id)
    q += " ORDER BY due_date ASC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/")
def create_event(event: EventCreate):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO calendar_events (matter_id, firm_id, title, event_type, due_date, due_time,
            location, description, attendees, status, reminder_days, is_court_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (event.matter_id, event.firm_id, event.title, event.event_type,
          event.due_date, event.due_time, event.location, event.description,
          event.attendees, event.status, event.reminder_days, int(event.is_court_date or 0)))
    conn.commit()
    row = conn.execute("SELECT * FROM calendar_events WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)

@router.put("/{event_id}")
def update_event(event_id: int, event: EventUpdate):
    conn = get_db()
    fields = {k: v for k, v in event.dict().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    if "is_court_date" in fields:
        fields["is_court_date"] = int(fields["is_court_date"])
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE calendar_events SET {set_clause} WHERE id = ?",
                 list(fields.values()) + [event_id])
    conn.commit()
    row = conn.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)

@router.delete("/{event_id}")
def delete_event(event_id: int):
    conn = get_db()
    conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return {"deleted": event_id}

@router.get("/types")
def get_event_types():
    return {"types": EVENT_TYPES, "statuses": STATUSES}
