import os
"""
legal_modules.py -- Depositions, Motions, Contracts routers
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.demo1.pg import get_conn


def init_legal_tables():
    """No-op -- tables exist in Supabase Postgres."""
    print("[LegalModules] Tables initialized OK")


# ── DEPOSITIONS ───────────────────────────────────────────────────────────────
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
def list_depositions(request: Request, case_number: str = None):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        if case_number:
            rows = conn.execute(
                "SELECT * FROM depositions WHERE firm_id=%s AND case_number=%s ORDER BY depo_date",
                (firm_id, case_number)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM depositions WHERE firm_id=%s ORDER BY depo_date",
                (firm_id,)
            ).fetchall()
    return {"total": len(rows), "depositions": [dict(r) for r in rows]}

@depo_router.get("/stats")
def depo_stats(request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        total    = conn.execute("SELECT COUNT(*) as c FROM depositions WHERE firm_id=%s", (firm_id,)).fetchone()["c"]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as count FROM depositions WHERE firm_id=%s GROUP BY status", (firm_id,)
        ).fetchall()
    return {"total": total, "by_status": {r["status"]: r["count"] for r in by_status}}

@depo_router.post("/")
def create_depo(body: DepoIn, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO depositions (firm_id,case_number,witness_name,witness_role,depo_date,location,status,notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (firm_id, body.case_number, body.witness_name, body.witness_role,
              body.depo_date, body.location, body.status, body.notes))
        row_id = cur.fetchone()["id"]
    return {"success": True, "id": row_id}

@depo_router.put("/{depo_id}")
def update_depo(depo_id: int, body: DepoIn, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        conn.execute("""
            UPDATE depositions SET witness_name=%s,witness_role=%s,depo_date=%s,
            location=%s,status=%s,notes=%s WHERE id=%s AND firm_id=%s
        """, (body.witness_name, body.witness_role, body.depo_date,
              body.location, body.status, body.notes, depo_id, firm_id))
    return {"success": True}

@depo_router.delete("/{depo_id}")
def delete_depo(depo_id: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        conn.execute("DELETE FROM depositions WHERE id=%s AND firm_id=%s", (depo_id, firm_id))
    return {"success": True}


# ── MOTIONS ───────────────────────────────────────────────────────────────────
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
def list_motions(request: Request, case_number: str = None):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        if case_number:
            rows = conn.execute(
                "SELECT * FROM motions WHERE firm_id=%s AND case_number=%s ORDER BY filed_date DESC",
                (firm_id, case_number)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM motions WHERE firm_id=%s ORDER BY filed_date DESC", (firm_id,)
            ).fetchall()
    return {"total": len(rows), "motions": [dict(r) for r in rows]}

@motion_router.get("/stats")
def motion_stats(request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        total     = conn.execute("SELECT COUNT(*) as c FROM motions WHERE firm_id=%s", (firm_id,)).fetchone()["c"]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as count FROM motions WHERE firm_id=%s GROUP BY status", (firm_id,)
        ).fetchall()
        by_type   = conn.execute(
            "SELECT motion_type, COUNT(*) as count FROM motions WHERE firm_id=%s GROUP BY motion_type", (firm_id,)
        ).fetchall()
    return {"total": total, "by_status": {r["status"]: r["count"] for r in by_status},
            "by_type": {r["motion_type"]: r["count"] for r in by_type}}

@motion_router.post("/")
def create_motion(body: MotionIn, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO motions (firm_id,case_number,title,motion_type,filed_date,hearing_date,status,notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (firm_id, body.case_number, body.title, body.motion_type,
              body.filed_date, body.hearing_date, body.status, body.notes))
        row_id = cur.fetchone()["id"]
    return {"success": True, "id": row_id}

@motion_router.put("/{motion_id}")
def update_motion(motion_id: int, body: MotionIn, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        conn.execute("""
            UPDATE motions SET title=%s,motion_type=%s,filed_date=%s,
            hearing_date=%s,status=%s,notes=%s WHERE id=%s AND firm_id=%s
        """, (body.title, body.motion_type, body.filed_date,
              body.hearing_date, body.status, body.notes, motion_id, firm_id))
    return {"success": True}

@motion_router.delete("/{motion_id}")
def delete_motion(motion_id: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        conn.execute("DELETE FROM motions WHERE id=%s AND firm_id=%s", (motion_id, firm_id))
    return {"success": True}


# ── CONTRACTS ─────────────────────────────────────────────────────────────────
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
def list_contracts(request: Request, case_number: str = None):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        if case_number:
            rows = conn.execute(
                "SELECT * FROM contracts WHERE firm_id=%s AND case_number=%s ORDER BY execution_date DESC",
                (firm_id, case_number)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM contracts WHERE firm_id=%s ORDER BY execution_date DESC", (firm_id,)
            ).fetchall()
    return {"total": len(rows), "contracts": [dict(r) for r in rows]}

@contract_router.get("/stats")
def contract_stats(request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        total     = conn.execute("SELECT COUNT(*) as c FROM contracts WHERE firm_id=%s", (firm_id,)).fetchone()["c"]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as count FROM contracts WHERE firm_id=%s GROUP BY status", (firm_id,)
        ).fetchall()
        by_type   = conn.execute(
            "SELECT contract_type, COUNT(*) as count FROM contracts WHERE firm_id=%s GROUP BY contract_type", (firm_id,)
        ).fetchall()
    return {"total": total, "by_status": {r["status"]: r["count"] for r in by_status},
            "by_type": {r["contract_type"]: r["count"] for r in by_type}}

@contract_router.post("/")
def create_contract(body: ContractIn, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO contracts
              (firm_id,case_number,contract_name,contract_type,parties,
               execution_date,expiry_date,status,notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (firm_id, body.case_number, body.contract_name, body.contract_type,
              body.parties, body.execution_date, body.expiry_date, body.status, body.notes))
        row_id = cur.fetchone()["id"]
    return {"success": True, "id": row_id}

@contract_router.put("/{contract_id}")
def update_contract(contract_id: int, body: ContractIn, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        conn.execute("""
            UPDATE contracts SET contract_name=%s,contract_type=%s,parties=%s,
            execution_date=%s,expiry_date=%s,status=%s,notes=%s
            WHERE id=%s AND firm_id=%s
        """, (body.contract_name, body.contract_type, body.parties,
              body.execution_date, body.expiry_date, body.status, body.notes,
              contract_id, firm_id))
    return {"success": True}

@contract_router.delete("/{contract_id}")
def delete_contract(contract_id: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        conn.execute("DELETE FROM contracts WHERE id=%s AND firm_id=%s", (contract_id, firm_id))
    return {"success": True}
