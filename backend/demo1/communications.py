"""
communications.py
=================
ParaIQ Communications Log (Phase 4)

Centralized logging for client emails and text messages linked to matters.
Provides the backend infrastructure for future Twilio/Outlook integrations.

Features:
  - Log inbound/outbound emails and SMS
  - Link communications to specific matters
  - Firm-isolated (RLS compliant)
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

def init_communications_tables():
    """Creates the communications log table if it doesn't exist (RLS-aware)."""
    try:
        from backend.demo1.pg import get_conn
        with get_conn("waw_vcf") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS communications (
                    id BIGSERIAL PRIMARY KEY,
                    firm_id TEXT NOT NULL,
                    matter_id BIGINT,
                    comm_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    sender TEXT,
                    recipient TEXT,
                    body TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            conn.execute("ALTER TABLE communications ENABLE ROW LEVEL SECURITY")
            conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE schemaname = 'public' AND tablename = 'communications'
                          AND policyname = 'communications_tenant_isolation'
                    ) THEN
                        CREATE POLICY communications_tenant_isolation ON communications
                            USING (firm_id = current_setting('app.current_firm_id', true))
                            WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
                    END IF;
                END
                $$
            """)
            conn.commit()
        print("[Comms] Communications table initialized ✓")
    except Exception as e:
        print(f"Error initializing comms tables: {e}")

def log_communication(
    firm_id: str, 
    comm_type: str, 
    direction: str, 
    sender: str, 
    recipient: str, 
    body: str, 
    matter_id: int = None
) -> Dict[str, Any]:
    """Logs an email or SMS to the database."""
    if comm_type not in ["email", "sms"]:
        return {"success": False, "error": "comm_type must be 'email' or 'sms'"}
    if direction not in ["inbound", "outbound"]:
        return {"success": False, "error": "direction must be 'inbound' or 'outbound'"}
        
    try:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                """INSERT INTO communications 
                   (firm_id, matter_id, comm_type, direction, sender, recipient, body)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id, created_at""",
                (firm_id, matter_id, comm_type, direction, sender, recipient, body)
            ).fetchone()
            return {"success": True, "comm_id": row[0], "created_at": str(row[1])}
    except Exception as e:
        logger.error(f"Error logging communication: {e}")
        return {"success": False, "error": str(e)}

def get_matter_communications(firm_id: str, matter_id: int) -> List[Dict[str, Any]]:
    """Retrieves all communications for a specific matter."""
    try:
        with get_conn(firm_id) as conn:
            rows = conn.execute(
                "SELECT * FROM communications WHERE firm_id = %s AND matter_id = %s ORDER BY created_at DESC",
                (firm_id, matter_id)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching communications: {e}")
        return []
