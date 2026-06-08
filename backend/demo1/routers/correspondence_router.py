from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id

router = APIRouter(prefix="/correspondence", tags=["correspondence"])


def init_table():
    """No-op — table exists in Supabase Postgres."""
    pass


init_table()


class CorrespondenceCreate(BaseModel):
    matter_id:  int
    type:       Optional[str] = "email"
    direction:  Optional[str] = "outbound"
    subject:    str
    body:       Optional[str] = ""
    from_party: Optional[str] = ""
    to_party:   Optional[str] = ""
    cc_party:   Optional[str] = ""
    date:       Optional[str] = None
    status:     Optional[str] = "draft"
    attachments: Optional[str] = ""


class CorrespondenceUpdate(BaseModel):
    type:       Optional[str] = None
    direction:  Optional[str] = None
    subject:    Optional[str] = None
    body:       Optional[str] = None
    from_party: Optional[str] = None
    to_party:   Optional[str] = None
    cc_party:   Optional[str] = None
    date:       Optional[str] = None
    status:     Optional[str] = None
    attachments: Optional[str] = None


@router.get("/{matter_id}")
def list_correspondence(
    matter_id: int,
    type:      Optional[str] = None,
    direction: Optional[str] = None,
    firm_id:   str           = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        sql    = "SELECT * FROM correspondence WHERE matter_id = %s"
        params = [matter_id]
        if type:
            sql += " AND type = %s"
            params.append(type)
        if direction:
            sql += " AND direction = %s"
            params.append(direction)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.post("/")
def create_correspondence(
    item:    CorrespondenceCreate,
    firm_id: str = Depends(get_current_firm_id),
):
    date_val = item.date or datetime.now().strftime("%Y-%m-%d")
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO correspondence
              (firm_id, matter_id, type, direction, subject, body,
               from_party, to_party, cc_party, date, status, attachments)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, item.matter_id, item.type, item.direction, item.subject,
              item.body, item.from_party, item.to_party, item.cc_party,
              date_val, item.status, item.attachments))
        new_id = cur.fetchone()["id"]
        row    = conn.execute(
            "SELECT * FROM correspondence WHERE id = %s", (new_id,)
        ).fetchone()
    return dict(row)


@router.put("/{item_id}")
def update_correspondence(
    item_id: int,
    item:    CorrespondenceUpdate,
    firm_id: str = Depends(get_current_firm_id),
):
    fields = {k: v for k, v in item.dict().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with get_conn(firm_id) as conn:
        conn.execute(
            f"UPDATE correspondence SET {set_clause} WHERE id = %s",
            list(fields.values()) + [item_id]
        )
        row = conn.execute(
            "SELECT * FROM correspondence WHERE id = %s", (item_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@router.delete("/{item_id}")
def delete_correspondence(
    item_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "DELETE FROM correspondence WHERE id = %s", (item_id,)
        )
    return {"deleted": item_id}
