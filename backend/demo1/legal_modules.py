"""
legal_modules.py — Depositions, Motions, Contracts routers
"""
import sqlite3, os
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DB = os.environ.get("PARAIQ_DB", str(__import__("pathlib").Path(__file__).parent / "analyses.db"))

def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ── Tables ────────────────────────────────────────────────────────────────────
def init_legal_tables():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS depositions (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        case_number    TEXT NOT NULL,
        witness_name   TEXT NOT NULL,
        witness_role   TEXT,
        depo_date      TEXT,
        location       TEXT,
        status         TEXT DEFAULT 'scheduled',
        notes          TEXT,
        created_at     TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS motions (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        case_number    TEXT NOT NULL,
        title          TEXT NOT NULL,
        motion_type    TEXT NOT NULL,
        filed_date     TEXT,
        hearing_date   TEXT,
        status         TEXT DEFAULT 'draft',
        notes          TEXT,
        created_at     TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS contracts (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        case_number    TEXT NOT NULL,
        contract_name  TEXT NOT NULL,
        contract_type  TEXT NOT NULL,
        parties        TEXT,
        execution_date TEXT,
        expiry_date    TEXT,
        status         TEXT DEFAULT 'draft',
        notes          TEXT,
        created_at     TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()
    conn.close()
    print("[LegalModules] Tables initialized ✓")

init_legal_tables()

# ══════════════════════════════════════════════════════════════════════════════
# DEPOSITIONS
# ══════════════════════════════════════════════════════════════════════════════
depo_router = APIRouter(prefix="/depositions", tags=["Depositions"])

class DepoIn(BaseModel):
    case_number:  str
    witness_name: str
    witness_role: Optional[str] = None
    depo_date:    Optional[str] = None
    location:     Optional[str] = None
    status:       Optional[str] = "scheduled"
    notes:        Optional[str] = None

@depo_router.get("/")
def list_depositions(case_number: str = None):
    conn = get_conn()
    if case_number:
        rows = conn.execute("SELECT * FROM depositions WHERE case_number=? ORDER BY depo_date", (case_number,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM depositions ORDER BY depo_date").fetchall()
    conn.close()
    return {"total": len(rows), "depositions": [dict(r) for r in rows]}

@depo_router.get("/stats")
def depo_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM depositions").fetchone()[0]
    by_status = conn.execute("SELECT status, COUNT(*) as count FROM depositions GROUP BY status").fetchall()
    conn.close()
    return {"total": total, "by_status": {r["status"]: r["count"] for r in by_status}}

@depo_router.post("/")
def create_depo(body: DepoIn):
    conn = get_conn()
    cur = conn.execute("""INSERT INTO depositions (case_number,witness_name,witness_role,depo_date,location,status,notes)
        VALUES (?,?,?,?,?,?,?)""",
        (body.case_number, body.witness_name, body.witness_role,
         body.depo_date, body.location, body.status, body.notes))
    conn.commit(); conn.close()
    return {"success": True, "id": cur.lastrowid}

@depo_router.put("/{depo_id}")
def update_depo(depo_id: int, body: DepoIn):
    conn = get_conn()
    conn.execute("""UPDATE depositions SET witness_name=?,witness_role=?,depo_date=?,location=?,status=?,notes=?
        WHERE id=?""", (body.witness_name, body.witness_role, body.depo_date,
                        body.location, body.status, body.notes, depo_id))
    conn.commit(); conn.close()
    return {"success": True}

@depo_router.delete("/{depo_id}")
def delete_depo(depo_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM depositions WHERE id=?", (depo_id,))
    conn.commit(); conn.close()
    return {"success": True}

# ══════════════════════════════════════════════════════════════════════════════
# MOTIONS
# ══════════════════════════════════════════════════════════════════════════════
motion_router = APIRouter(prefix="/motions", tags=["Motions"])

class MotionIn(BaseModel):
    case_number:  str
    title:        str
    motion_type:  str
    filed_date:   Optional[str] = None
    hearing_date: Optional[str] = None
    status:       Optional[str] = "draft"
    notes:        Optional[str] = None

@motion_router.get("/")
def list_motions(case_number: str = None):
    conn = get_conn()
    if case_number:
        rows = conn.execute("SELECT * FROM motions WHERE case_number=? ORDER BY filed_date DESC", (case_number,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM motions ORDER BY filed_date DESC").fetchall()
    conn.close()
    return {"total": len(rows), "motions": [dict(r) for r in rows]}

@motion_router.get("/stats")
def motion_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM motions").fetchone()[0]
    by_status = conn.execute("SELECT status, COUNT(*) as count FROM motions GROUP BY status").fetchall()
    by_type   = conn.execute("SELECT motion_type, COUNT(*) as count FROM motions GROUP BY motion_type").fetchall()
    conn.close()
    return {"total": total, "by_status": {r["status"]: r["count"] for r in by_status},
            "by_type": {r["motion_type"]: r["count"] for r in by_type}}

@motion_router.post("/")
def create_motion(body: MotionIn):
    conn = get_conn()
    cur = conn.execute("""INSERT INTO motions (case_number,title,motion_type,filed_date,hearing_date,status,notes)
        VALUES (?,?,?,?,?,?,?)""",
        (body.case_number, body.title, body.motion_type,
         body.filed_date, body.hearing_date, body.status, body.notes))
    conn.commit(); conn.close()
    return {"success": True, "id": cur.lastrowid}

@motion_router.put("/{motion_id}")
def update_motion(motion_id: int, body: MotionIn):
    conn = get_conn()
    conn.execute("""UPDATE motions SET title=?,motion_type=?,filed_date=?,hearing_date=?,status=?,notes=?
        WHERE id=?""", (body.title, body.motion_type, body.filed_date,
                        body.hearing_date, body.status, body.notes, motion_id))
    conn.commit(); conn.close()
    return {"success": True}

@motion_router.delete("/{motion_id}")
def delete_motion(motion_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM motions WHERE id=?", (motion_id,))
    conn.commit(); conn.close()
    return {"success": True}

# ══════════════════════════════════════════════════════════════════════════════
# CONTRACTS
# ══════════════════════════════════════════════════════════════════════════════
contract_router = APIRouter(prefix="/contracts", tags=["Contracts"])

class ContractIn(BaseModel):
    case_number:    str
    contract_name:  str
    contract_type:  str
    parties:        Optional[str] = None
    execution_date: Optional[str] = None
    expiry_date:    Optional[str] = None
    status:         Optional[str] = "draft"
    notes:          Optional[str] = None

@contract_router.get("/")
def list_contracts(case_number: str = None):
    conn = get_conn()
    if case_number:
        rows = conn.execute("SELECT * FROM contracts WHERE case_number=? ORDER BY execution_date DESC", (case_number,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contracts ORDER BY execution_date DESC").fetchall()
    conn.close()
    return {"total": len(rows), "contracts": [dict(r) for r in rows]}

@contract_router.get("/stats")
def contract_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
    by_status = conn.execute("SELECT status, COUNT(*) as count FROM contracts GROUP BY status").fetchall()
    by_type   = conn.execute("SELECT contract_type, COUNT(*) as count FROM contracts GROUP BY contract_type").fetchall()
    conn.close()
    return {"total": total, "by_status": {r["status"]: r["count"] for r in by_status},
            "by_type": {r["contract_type"]: r["count"] for r in by_type}}

@contract_router.post("/")
def create_contract(body: ContractIn):
    conn = get_conn()
    cur = conn.execute("""INSERT INTO contracts (case_number,contract_name,contract_type,parties,execution_date,expiry_date,status,notes)
        VALUES (?,?,?,?,?,?,?,?)""",
        (body.case_number, body.contract_name, body.contract_type, body.parties,
         body.execution_date, body.expiry_date, body.status, body.notes))
    conn.commit(); conn.close()
    return {"success": True, "id": cur.lastrowid}

@contract_router.put("/{contract_id}")
def update_contract(contract_id: int, body: ContractIn):
    conn = get_conn()
    conn.execute("""UPDATE contracts SET contract_name=?,contract_type=?,parties=?,execution_date=?,expiry_date=?,status=?,notes=?
        WHERE id=?""", (body.contract_name, body.contract_type, body.parties,
                        body.execution_date, body.expiry_date, body.status, body.notes, contract_id))
    conn.commit(); conn.close()
    return {"success": True}

@contract_router.delete("/{contract_id}")
def delete_contract(contract_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
    conn.commit(); conn.close()
    return {"success": True}
