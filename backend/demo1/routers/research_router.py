from fastapi import APIRouter, HTTPException, Depends
from backend.demo1.auth import get_current_firm_id
from backend.demo1.pg import get_conn
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/research", tags=["research"])

RESEARCH_TYPES = ["case_law", "statute", "regulation", "secondary", "memo", "brief", "other"]


def init_table():
    """No-op — table exists in Supabase Postgres."""
    pass


init_table()


class ResearchCreate(BaseModel):
    matter_id:     Optional[int]  = None
    title:         str
    research_type: Optional[str]  = "case_law"
    citation:      Optional[str]  = ""
    jurisdiction:  Optional[str]  = ""
    summary:       Optional[str]  = ""
    body:          Optional[str]  = ""
    relevance:     Optional[str]  = ""
    url:           Optional[str]  = ""
    tags:          Optional[str]  = ""
    is_favorable:  Optional[bool] = True
    created_by:    Optional[str]  = ""


class ResearchUpdate(BaseModel):
    title:         Optional[str]  = None
    research_type: Optional[str]  = None
    citation:      Optional[str]  = None
    jurisdiction:  Optional[str]  = None
    summary:       Optional[str]  = None
    body:          Optional[str]  = None
    relevance:     Optional[str]  = None
    url:           Optional[str]  = None
    tags:          Optional[str]  = None
    is_favorable:  Optional[bool] = None


@router.get("/matter/{matter_id}")
def list_matter_research(
    matter_id:     int,
    research_type: Optional[str]  = None,
    is_favorable:  Optional[bool] = None,
    firm_id:       str            = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        sql    = "SELECT * FROM research_notes WHERE matter_id = %s"
        params = [matter_id]
        if research_type:
            sql += " AND research_type = %s"
            params.append(research_type)
        if is_favorable is not None:
            sql += " AND is_favorable = %s"
            params.append(is_favorable)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/firm/{firm_id_path}")
def list_firm_research(
    firm_id_path: str,
    search:       Optional[str] = None,
    firm_id:      str           = Depends(get_current_firm_id),
):
    # firm_id_path ignored — RLS enforces tenant isolation
    with get_conn(firm_id) as conn:
        sql    = "SELECT * FROM research_notes WHERE TRUE"
        params = []
        if search:
            sql += " AND (title ILIKE %s OR citation ILIKE %s OR summary ILIKE %s OR tags ILIKE %s)"
            s = f"%{search}%"
            params += [s, s, s, s]
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/{note_id}")
def get_research_note(
    note_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT * FROM research_notes WHERE id = %s", (note_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@router.post("/")
def create_research_note(
    note:    ResearchCreate,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO research_notes
              (firm_id, matter_id, title, research_type, citation, jurisdiction,
               summary, body, relevance, url, tags, is_favorable, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, note.matter_id, note.title, note.research_type,
              note.citation, note.jurisdiction, note.summary, note.body,
              note.relevance, note.url, note.tags,
              note.is_favorable if note.is_favorable is not None else True,
              note.created_by))
        new_id = cur.fetchone()["id"]
        row    = conn.execute(
            "SELECT * FROM research_notes WHERE id = %s", (new_id,)
        ).fetchone()
    return dict(row)


@router.put("/{note_id}")
def update_research_note(
    note_id: int,
    note:    ResearchUpdate,
    firm_id: str = Depends(get_current_firm_id),
):
    fields = {k: v for k, v in note.dict().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with get_conn(firm_id) as conn:
        conn.execute(
            f"UPDATE research_notes SET {set_clause} WHERE id = %s",
            list(fields.values()) + [note_id]
        )
        row = conn.execute(
            "SELECT * FROM research_notes WHERE id = %s", (note_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@router.delete("/{note_id}")
def delete_research_note(
    note_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "DELETE FROM research_notes WHERE id = %s", (note_id,)
        )
    return {"deleted": note_id}


@router.get("/types/list")
def get_research_types():
    return {"types": RESEARCH_TYPES}
