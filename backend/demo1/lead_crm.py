"""
lead_crm.py
===========
ParaIQ Lead & CRM Pipeline (Phase 4)

Tracks prospects from first contact to engagement letter signing.
This module manages the lead lifecycle and integrates with the e-signature
module for final conversion.

Features:
  - Lead creation and tracking
  - Status pipeline management (New, Contacted, Qualified, Won, Lost)
  - Firm-isolated (RLS compliant)
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

def init_crm_tables():
    """Creates the leads table if it doesn't exist."""
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv("/root/nlp-portfolio/.env")
        import psycopg2
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS public.leads (
                id BIGSERIAL PRIMARY KEY,
                firm_id TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                phone TEXT,
                case_description TEXT,
                status TEXT DEFAULT 'New',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
        """)
        cursor.close()
        conn.close()
        print("[CRM] Leads table initialized [OK]")
    except Exception as e:
        print(f"Error initializing CRM tables: {e}")

def create_lead(firm_id: str, first_name: str, last_name: str, email: str = "", phone: str = "", case_description: str = "") -> Dict[str, Any]:
    """Creates a new lead in the CRM."""
    try:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                """INSERT INTO leads (firm_id, first_name, last_name, email, phone, case_description, status)
                   VALUES (%s, %s, %s, %s, %s, %s, 'New') RETURNING id, created_at""",
                (firm_id, first_name, last_name, email, phone, case_description)
            ).fetchone()
            return {"success": True, "lead_id": row[0], "created_at": str(row[1])}
    except Exception as e:
        logger.error(f"Error creating lead for {firm_id}: {e}")
        return {"success": False, "error": str(e)}

def get_leads(firm_id: str, status: str = None) -> List[Dict[str, Any]]:
    """Retrieves leads for a firm, optionally filtered by status."""
    try:
        with get_conn(firm_id) as conn:
            if status:
                rows = conn.execute("SELECT * FROM leads WHERE firm_id = %s AND status = %s ORDER BY created_at DESC", (firm_id, status)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM leads WHERE firm_id = %s ORDER BY created_at DESC", (firm_id,)).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching leads for {firm_id}: {e}")
        return []

def update_lead_status(firm_id: str, lead_id: int, new_status: str) -> Dict[str, Any]:
    """Updates the status of a lead."""
    valid_statuses = ["New", "Contacted", "Qualified", "Won", "Lost"]
    if new_status not in valid_statuses:
        return {"success": False, "error": f"Invalid status. Must be one of {valid_statuses}"}
    try:
        with get_conn(firm_id) as conn:
            res = conn.execute(
                "UPDATE leads SET status = %s, updated_at = %s WHERE id = %s AND firm_id = %s",
                (new_status, datetime.now(timezone.utc), lead_id, firm_id)
            )
            if res.rowcount == 0:
                return {"success": False, "error": "Lead not found or access denied"}
            return {"success": True, "lead_id": lead_id, "new_status": new_status}
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")
        return {"success": False, "error": str(e)}
