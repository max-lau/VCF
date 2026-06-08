from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id

router = APIRouter(prefix="/contacts", tags=["contacts"])

ROLES = ["client", "witness", "expert", "opposing_counsel", "opposing_party",
         "judge", "mediator", "paralegal", "co_counsel", "vendor", "other"]


def init_table():
    """No-op — tables exist in Supabase Postgres."""
    pass


init_table()


class ContactCreate(BaseModel):
    matter_id:    Optional[int]  = None
    name:         str
    role:         Optional[str]  = "other"
    organization: Optional[str]  = ""
    email:        Optional[str]  = ""
    phone:        Optional[str]  = ""
    address:      Optional[str]  = ""
    notes:        Optional[str]  = ""
    is_adverse:   Optional[bool] = False
    tags:         Optional[str]  = ""


class ContactUpdate(BaseModel):
    name:         Optional[str]  = None
    role:         Optional[str]  = None
    organization: Optional[str]  = None
    email:        Optional[str]  = None
    phone:        Optional[str]  = None
    address:      Optional[str]  = None
    notes:        Optional[str]  = None
    is_adverse:   Optional[bool] = None
    tags:         Optional[str]  = None


@router.get("/firm/{firm_id_path}")
def list_firm_contacts(
    firm_id_path: str,
    role:         Optional[str] = None,
    search:       Optional[str] = None,
    firm_id:      str           = Depends(get_current_firm_id),
):
    # firm_id_path ignored — RLS enforces tenant isolation via JWT firm_id
    with get_conn(firm_id) as conn:
        sql    = "SELECT * FROM contacts WHERE TRUE"
        params = []
        if role:
            sql += " AND role = %s"
            params.append(role)
        if search:
            sql += " AND (name ILIKE %s OR email ILIKE %s OR organization ILIKE %s)"
            s = f"%{search}%"
            params += [s, s, s]
        sql += " ORDER BY name ASC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/matter/{matter_id}")
def list_matter_contacts(
    matter_id: int,
    firm_id:   str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        # Contacts linked via junction table
        joined = conn.execute("""
            SELECT c.*, cm.role AS matter_role
            FROM contacts c
            JOIN contact_matters cm ON c.id = cm.contact_id
            WHERE cm.matter_id = %s
            ORDER BY c.name ASC
        """, (matter_id,)).fetchall()

        # Contacts with matter_id set directly
        direct = conn.execute("""
            SELECT *, role AS matter_role FROM contacts
            WHERE matter_id = %s ORDER BY name ASC
        """, (matter_id,)).fetchall()

    seen, result = set(), []
    for r in list(joined) + list(direct):
        d = dict(r)
        if d["id"] not in seen:
            seen.add(d["id"])
            result.append(d)
    return result


@router.post("/")
def create_contact(
    contact: ContactCreate,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO contacts
              (firm_id, matter_id, name, role, organization, email,
               phone, address, notes, is_adverse, tags)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, contact.matter_id, contact.name, contact.role,
              contact.organization, contact.email, contact.phone,
              contact.address, contact.notes,
              contact.is_adverse or False, contact.tags))
        cid = cur.fetchone()["id"]

        if contact.matter_id:
            conn.execute("""
                INSERT INTO contact_matters (firm_id, contact_id, matter_id, role)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (firm_id, cid, contact.matter_id, contact.role))

        row = conn.execute(
            "SELECT * FROM contacts WHERE id = %s", (cid,)
        ).fetchone()
    return dict(row)


@router.post("/{contact_id}/link/{matter_id}")
def link_contact_to_matter(
    contact_id: int,
    matter_id:  int,
    role:       Optional[str] = "other",
    firm_id:    str           = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute("""
            INSERT INTO contact_matters (firm_id, contact_id, matter_id, role)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (firm_id, contact_id, matter_id) DO UPDATE SET role = EXCLUDED.role
        """, (firm_id, contact_id, matter_id, role))
    return {"linked": True}


@router.put("/{contact_id}")
def update_contact(
    contact_id: int,
    contact:    ContactUpdate,
    firm_id:    str = Depends(get_current_firm_id),
):
    fields = {k: v for k, v in contact.dict().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with get_conn(firm_id) as conn:
        conn.execute(
            f"UPDATE contacts SET {set_clause} WHERE id = %s",
            list(fields.values()) + [contact_id]
        )
        row = conn.execute(
            "SELECT * FROM contacts WHERE id = %s", (contact_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@router.delete("/{contact_id}")
def delete_contact(
    contact_id: int,
    firm_id:    str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "DELETE FROM contact_matters WHERE contact_id = %s", (contact_id,)
        )
        conn.execute(
            "DELETE FROM contacts WHERE id = %s", (contact_id,)
        )
    return {"deleted": contact_id}


@router.get("/roles")
def get_roles():
    return {"roles": ROLES}
