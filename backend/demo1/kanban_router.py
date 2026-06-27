from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date
import logging

from backend.demo1.auth import get_current_user, get_current_firm_id
from backend.demo1.pg import get_conn

router = APIRouter()
log = logging.getLogger(__name__)

COLUMNS = ["intake", "research", "discovery", "motions", "trial_prep", "closed"]
CARD_TYPES = ["task", "deadline", "motion", "depo", "filing"]

class CardCreate(BaseModel):
    case_id: int
    title: str
    card_type: str
    column_id: str
    due_date: Optional[date] = None
    assignee_id: Optional[int] = None
    notes: Optional[str] = None
    position: Optional[int] = 0

class CardMove(BaseModel):
    column_id: str
    position: Optional[int] = 0
    moved_by_hermes: bool = False
    hermes_reason: Optional[str] = None

class CardUpdate(BaseModel):
    title: Optional[str] = None
    card_type: Optional[str] = None
    due_date: Optional[date] = None
    assignee_id: Optional[int] = None
    notes: Optional[str] = None

class HermesSignal(BaseModel):
    case_id: int
    card_id: int
    detected_event: str
    suggested_column: str
    confidence: float

def row_to_dict(row, cursor):
    return dict(zip([d[0] for d in cursor.description], row))

@router.get("/kanban/cases/{case_id}/board")
def get_board(case_id: int, firm_id: str = Depends(get_current_firm_id)):
    print(f"DEBUG get_board case_id={case_id} firm_id={firm_id}", flush=True)
    with get_conn(firm_id) as conn:
        cur = conn.execute(
            """SELECT id, case_id, firm_id, title, card_type, column_id,
                      due_date, assignee_id, notes, position, moved_by_hermes,
                      created_at, updated_at
               FROM kanban_cards
               WHERE case_id=%s AND firm_id=%s
               ORDER BY column_id, position ASC""",
            (case_id, firm_id))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        print(f"DEBUG rows={len(rows)} cols={cols}", flush=True)

    grouped = {col: [] for col in COLUMNS}
    for row in rows:
        d = dict(row)
        if d.get("due_date"):
            d["due_date"] = str(d["due_date"])
        if d.get("created_at"):
            d["created_at"] = str(d["created_at"])
        if d.get("updated_at"):
            d["updated_at"] = str(d["updated_at"])
        col = d["column_id"]
        if col in grouped:
            grouped[col].append(d)
    return {"columns": COLUMNS, "cards": grouped}

@router.post("/kanban/cases/{case_id}/cards")
def create_card(case_id: int, body: CardCreate,
                user=Depends(get_current_user),
                firm_id: str = Depends(get_current_firm_id)):
    if body.card_type not in CARD_TYPES:
        raise HTTPException(400, f"card_type must be one of {CARD_TYPES}")
    if body.column_id not in COLUMNS:
        raise HTTPException(400, f"column_id must be one of {COLUMNS}")
    try:
        with get_conn(firm_id) as conn:
            cur = conn.execute(
                """INSERT INTO kanban_cards
                   (case_id, firm_id, title, card_type, column_id, due_date,
                    assignee_id, notes, position, moved_by_hermes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,false)
                   RETURNING id, created_at""",
                (case_id, firm_id, body.title, body.card_type, body.column_id,
                 body.due_date, body.assignee_id, body.notes, body.position))
            row = cur.fetchone()
        return {"id": row["id"], "created_at": str(row["created_at"])}
    except (psycopg2.Error, KeyError, ValueError, TypeError) as e:
        import traceback; traceback.print_exc()
        import logging; logging.getLogger(__name__).error(f"[kanban_router] Error: {e}")
        raise HTTPException(500, detail="An internal error occurred. Please try again.")

@router.patch("/kanban/cases/{case_id}/cards/{card_id}/move")
def move_card(case_id: int, card_id: int, body: CardMove,
              user=Depends(get_current_user),
              firm_id: str = Depends(get_current_firm_id)):
    if body.column_id not in COLUMNS:
        raise HTTPException(400, f"column_id must be one of {COLUMNS}")
    with get_conn(firm_id) as conn:
        cur = conn.execute(
            "SELECT column_id FROM kanban_cards WHERE id=%s AND case_id=%s AND firm_id=%s",
            (card_id, case_id, firm_id))
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(404, "Card not found")
        old_col = existing["column_id"]
        conn.execute(
            """UPDATE kanban_cards
               SET column_id=%s, position=%s, moved_by_hermes=%s, updated_at=NOW()
               WHERE id=%s""",
            (body.column_id, body.position, body.moved_by_hermes, card_id))
        conn.execute(
            """INSERT INTO kanban_card_logs
               (card_id, case_id, firm_id, from_column, to_column,
                moved_by_hermes, hermes_reason, moved_by_user_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (card_id, case_id, firm_id, old_col, body.column_id,
             body.moved_by_hermes, body.hermes_reason,
             user["id"] if not body.moved_by_hermes else None))
    return {"ok": True, "from": old_col, "to": body.column_id}

@router.patch("/kanban/cases/{case_id}/cards/{card_id}")
def update_card(case_id: int, card_id: int, body: CardUpdate,
                user=Depends(get_current_user),
                firm_id: str = Depends(get_current_firm_id)):
    fields, values = [], []
    if body.title is not None:
        fields.append("title=%s"); values.append(body.title)
    if body.card_type is not None:
        fields.append("card_type=%s"); values.append(body.card_type)
    if body.due_date is not None:
        fields.append("due_date=%s"); values.append(body.due_date)
    if body.assignee_id is not None:
        fields.append("assignee_id=%s"); values.append(body.assignee_id)
    if body.notes is not None:
        fields.append("notes=%s"); values.append(body.notes)
    if not fields:
        raise HTTPException(400, "No fields to update")
    fields.append("updated_at=NOW()")
    values.extend([card_id, firm_id])
    with get_conn(firm_id) as conn:
        conn.execute(
            f"UPDATE kanban_cards SET {', '.join(fields)} WHERE id=%s AND firm_id=%s",
            values)
    return {"ok": True}

@router.delete("/kanban/cases/{case_id}/cards/{card_id}")
def delete_card(case_id: int, card_id: int,
                user=Depends(get_current_user),
                firm_id: str = Depends(get_current_firm_id)):
    with get_conn(firm_id) as conn:
        cur = conn.execute(
            "DELETE FROM kanban_cards WHERE id=%s AND case_id=%s AND firm_id=%s RETURNING id",
            (card_id, case_id, firm_id))
        if not cur.fetchone():
            raise HTTPException(404, "Card not found")
    return {"ok": True}

@router.get("/kanban/cases/{case_id}/cards/{card_id}/log")
def get_card_log(case_id: int, card_id: int,
                 firm_id: str = Depends(get_current_firm_id)):
    with get_conn(firm_id) as conn:
        cur = conn.execute(
            """SELECT from_column, to_column, moved_by_hermes,
                      hermes_reason, moved_at
               FROM kanban_card_logs
               WHERE card_id=%s AND firm_id=%s
               ORDER BY moved_at DESC""",
            (card_id, firm_id))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return [dict(r) for r in rows]

@router.post("/kanban/hermes/signal")
def hermes_signal(body: HermesSignal,
                  firm_id: str = Depends(get_current_firm_id)):
    if body.suggested_column not in COLUMNS:
        raise HTTPException(400, "Invalid column")
    auto_move = body.confidence >= 0.8
    if auto_move:
        with get_conn(firm_id) as conn:
            cur = conn.execute(
                "SELECT column_id FROM kanban_cards WHERE id=%s AND firm_id=%s",
                (body.card_id, firm_id))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(404, "Card not found")
            old_col = existing["column_id"]
            conn.execute(
                "UPDATE kanban_cards SET column_id=%s, moved_by_hermes=true, updated_at=NOW() WHERE id=%s",
                (body.suggested_column, body.card_id))
            conn.execute(
                """INSERT INTO kanban_card_logs
                   (card_id, case_id, firm_id, from_column, to_column,
                    moved_by_hermes, hermes_reason, moved_by_user_id)
                   VALUES (%s,%s,%s,%s,%s,true,%s,NULL)""",
                (body.card_id, body.case_id, firm_id,
                 old_col, body.suggested_column, body.detected_event))
        return {"action": "moved", "from": old_col, "to": body.suggested_column}
    return {"action": "flagged_for_review",
            "suggested_column": body.suggested_column,
            "confidence": body.confidence}
