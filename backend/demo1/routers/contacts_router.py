from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import sqlite3, os

router = APIRouter(prefix="/contacts", tags=["contacts"])

DB_PATH = os.environ.get("DB_PATH", "/root/nlp-portfolio/analyses.db")

ROLES = ["client", "witness", "expert", "opposing_counsel", "opposing_party",
         "judge", "mediator", "paralegal", "co_counsel", "vendor", "other"]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firm_id INTEGER,
            matter_id INTEGER,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'other',
            organization TEXT,
            email TEXT,
            phone TEXT,
            address TEXT,
            notes TEXT,
            is_adverse INTEGER DEFAULT 0,
            tags TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # Junction table — one contact can appear on multiple matters
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_matters (
            contact_id INTEGER NOT NULL,
            matter_id INTEGER NOT NULL,
            role TEXT,
            PRIMARY KEY (contact_id, matter_id)
        )
    """)
    conn.commit()
    conn.close()

init_table()

class ContactCreate(BaseModel):
    firm_id: Optional[int] = None
    matter_id: Optional[int] = None
    name: str
    role: Optional[str] = "other"
    organization: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""
    notes: Optional[str] = ""
    is_adverse: Optional[bool] = False
    tags: Optional[str] = ""

class ContactUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    organization: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_adverse: Optional[bool] = None
    tags: Optional[str] = None

@router.get("/firm/{firm_id}")
def list_firm_contacts(firm_id: int, role: Optional[str] = None, search: Optional[str] = None):
    conn = get_db()
    q = "SELECT * FROM contacts WHERE firm_id = ?"
    params = [firm_id]
    if role:
        q += " AND role = ?"
        params.append(role)
    if search:
        q += " AND (name LIKE ? OR email LIKE ? OR organization LIKE ?)"
        s = f"%{search}%"
        params += [s, s, s]
    q += " ORDER BY name ASC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/matter/{matter_id}")
def list_matter_contacts(matter_id: int):
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*, cm.role as matter_role FROM contacts c
        JOIN contact_matters cm ON c.id = cm.contact_id
        WHERE cm.matter_id = ?
        ORDER BY c.name ASC
    """, (matter_id,)).fetchall()
    # Also include contacts where matter_id is set directly
    direct = conn.execute(
        "SELECT *, role as matter_role FROM contacts WHERE matter_id = ? ORDER BY name ASC",
        (matter_id,)
    ).fetchall()
    conn.close()
    seen = set()
    result = []
    for r in list(rows) + list(direct):
        d = dict(r)
        if d["id"] not in seen:
            seen.add(d["id"])
            result.append(d)
    return result

@router.post("/")
def create_contact(contact: ContactCreate):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO contacts (firm_id, matter_id, name, role, organization, email,
            phone, address, notes, is_adverse, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact.firm_id, contact.matter_id, contact.name, contact.role,
          contact.organization, contact.email, contact.phone, contact.address,
          contact.notes, int(contact.is_adverse or 0), contact.tags))
    cid = cur.lastrowid
    # Auto-link to matter if provided
    if contact.matter_id:
        conn.execute("INSERT OR IGNORE INTO contact_matters (contact_id, matter_id, role) VALUES (?, ?, ?)",
                     (cid, contact.matter_id, contact.role))
    conn.commit()
    row = conn.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone()
    conn.close()
    return dict(row)

@router.post("/{contact_id}/link/{matter_id}")
def link_contact_to_matter(contact_id: int, matter_id: int, role: Optional[str] = "other"):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO contact_matters (contact_id, matter_id, role) VALUES (?, ?, ?)",
                 (contact_id, matter_id, role))
    conn.commit()
    conn.close()
    return {"linked": True}

@router.put("/{contact_id}")
def update_contact(contact_id: int, contact: ContactUpdate):
    conn = get_db()
    fields = {k: v for k, v in contact.dict().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    if "is_adverse" in fields:
        fields["is_adverse"] = int(fields["is_adverse"])
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE contacts SET {set_clause} WHERE id = ?",
                 list(fields.values()) + [contact_id])
    conn.commit()
    row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)

@router.delete("/{contact_id}")
def delete_contact(contact_id: int):
    conn = get_db()
    conn.execute("DELETE FROM contact_matters WHERE contact_id = ?", (contact_id,))
    conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    conn.commit()
    conn.close()
    return {"deleted": contact_id}

@router.get("/roles")
def get_roles():
    return {"roles": ROLES}
