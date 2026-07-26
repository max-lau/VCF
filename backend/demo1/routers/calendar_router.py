from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id

router = APIRouter(prefix="/calendar", tags=["calendar"])

EVENT_TYPES = ["deadline", "vcf_deadline", "medical_appointment", "client_followup",
               "document_request", "claim_milestone", "meeting", "other"]
STATUSES    = ["upcoming", "completed", "cancelled", "rescheduled"]


def init_table():
    """No-op — table exists in Supabase Postgres."""
    pass


init_table()


class EventCreate(BaseModel):
    case_id:       Optional[int] = None
    title:         str
    event_type:    Optional[str]  = "deadline"
    due_date:      str
    due_time:      Optional[str]  = None
    location:      Optional[str]  = ""
    description:   Optional[str]  = ""
    attendees:     Optional[str]  = ""
    status:        Optional[str]  = "upcoming"
    reminder_days: Optional[int] = 3


class EventUpdate(BaseModel):
    case_id:       Optional[int]  = None
    title:         Optional[str]  = None
    event_type:    Optional[str]  = None
    due_date:      Optional[str]  = None
    due_time:      Optional[str]  = None
    location:      Optional[str]  = None
    description:   Optional[str]  = None
    attendees:     Optional[str]  = None
    status:        Optional[str]  = None
    reminder_days: Optional[int]  = None


@router.get("/case/{case_id}")
def list_case_events(
    case_id: int,
    status:  Optional[str] = None,
    firm_id: str           = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        sql    = "SELECT * FROM calendar_events WHERE case_id = %s"
        params = [case_id]
        if status:
            sql += " AND status = %s"
            params.append(status)
        sql += " ORDER BY due_date ASC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/firm/{firm_id_path}")
def list_firm_events(
    firm_id_path: str,
    days_ahead:   int          = 30,
    status:       Optional[str] = None,
    firm_id:      str           = Depends(get_current_firm_id),
):
    # firm_id_path ignored — RLS enforces tenant isolation via JWT firm_id
    cutoff = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    today  = datetime.now().strftime("%Y-%m-%d")
    with get_conn(firm_id) as conn:
        sql    = "SELECT * FROM calendar_events WHERE due_date BETWEEN %s AND %s"
        params = [today, cutoff]
        if status:
            sql += " AND status = %s"
            params.append(status)
        sql += " ORDER BY due_date ASC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/upcoming")
def upcoming_events(
    days_ahead: int          = 7,
    firm_id:    str          = Depends(get_current_firm_id),
):
    cutoff = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    today  = datetime.now().strftime("%Y-%m-%d")
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT * FROM calendar_events
            WHERE due_date BETWEEN %s AND %s
              AND firm_id = %s
              AND status NOT IN ('completed', 'cancelled')
            ORDER BY due_date ASC
        """, [today, cutoff, firm_id]).fetchall()
    return [dict(r) for r in rows]


@router.post("/")
def create_event(
    event:   EventCreate,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO calendar_events
              (firm_id, case_id, title, event_type, due_date, due_time,
               location, description, attendees, status, reminder_days)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, event.case_id, event.title, event.event_type,
              event.due_date, event.due_time, event.location, event.description,
              event.attendees, event.status, event.reminder_days))
        new_id = cur.fetchone()["id"]
        row    = conn.execute(
            "SELECT * FROM calendar_events WHERE id = %s", (new_id,)
        ).fetchone()
    return dict(row)


@router.put("/{event_id}")
def update_event(
    event_id: int,
    event:    EventUpdate,
    firm_id:  str = Depends(get_current_firm_id),
):
    fields = {k: v for k, v in event.dict().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with get_conn(firm_id) as conn:
        conn.execute(
            f"UPDATE calendar_events SET {set_clause} WHERE id = %s",
            list(fields.values()) + [event_id]
        )
        row = conn.execute(
            "SELECT * FROM calendar_events WHERE id = %s", (event_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@router.delete("/{event_id}")
def delete_event(
    event_id: int,
    firm_id:  str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "DELETE FROM calendar_events WHERE id = %s", (event_id,)
        )
    return {"deleted": event_id}


@router.get("/types")
def get_event_types():
    return {"types": EVENT_TYPES, "statuses": STATUSES}
