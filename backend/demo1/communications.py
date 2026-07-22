"""
communications.py
=================
Unified communications log for VCFClaimsIQ.

Tracks inbound/outbound communications across clients, labs, doctors,
Medicare/Medicaid, banks, the VCF, and the law office.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Communications"])


PARTY_TYPES = {
    "client",
    "lab",
    "doctor",
    "medicare",
    "medicaid",
    "bank",
    "vcf",
    "office",
    "other",
}

CHANNELS = {"email", "phone", "fax", "mail", "sms", "in_person", "other"}


class LogCommunicationBody(BaseModel):
    case_id: int
    direction: str = Field(..., pattern="^(inbound|outbound)$")
    channel: str
    party_type: str
    party_name: Optional[str] = ""
    sender: Optional[str] = ""
    recipient: Optional[str] = ""
    subject: Optional[str] = ""
    body: Optional[str] = ""
    sent_at: Optional[str] = ""


class ListCommunicationsParams(BaseModel):
    case_id: Optional[int] = None
    party_type: Optional[str] = None
    channel: Optional[str] = None
    days: Optional[int] = 30


def init_communications_tables():
    """Creates the communications log table if it doesn't exist (RLS-aware)."""
    try:
        from backend.demo1.pg import get_conn
        with get_conn("waw_vcf") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS communications (
                    id BIGSERIAL PRIMARY KEY,
                    firm_id TEXT NOT NULL,
                    case_id BIGINT,
                    direction TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    party_type TEXT NOT NULL,
                    party_name TEXT,
                    sender TEXT,
                    recipient TEXT,
                    subject TEXT,
                    body TEXT,
                    sent_at TIMESTAMPTZ DEFAULT NOW(),
                    created_by TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            conn.execute("ALTER TABLE communications ENABLE ROW LEVEL SECURITY")
            conn.execute("ALTER TABLE communications ADD COLUMN IF NOT EXISTS created_by TEXT")
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
    matter_id: int = None,
) -> Dict[str, Any]:
    """Legacy helper: logs an email or SMS to the database."""
    if comm_type not in ["email", "sms"]:
        return {"success": False, "error": "comm_type must be 'email' or 'sms'"}
    if direction not in ["inbound", "outbound"]:
        return {"success": False, "error": "direction must be 'inbound' or 'outbound'"}

    try:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                """INSERT INTO communications
                   (firm_id, case_id, channel, direction, party_type, party_name, sender, recipient, subject, body)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, created_at""",
                (firm_id, matter_id, comm_type, direction, "other", "",
                 sender, recipient, "", body),
            ).fetchone()
            conn.commit()
            return {"success": True, "comm_id": row[0], "created_at": str(row[1])}
    except Exception as e:
        logger.error(f"Error logging communication: {e}")
        return {"success": False, "error": str(e)}


def get_matter_communications(firm_id: str, matter_id: int) -> List[Dict[str, Any]]:
    """Legacy helper: retrieves all communications for a specific matter."""
    try:
        with get_conn(firm_id) as conn:
            rows = conn.execute(
                """SELECT * FROM communications
                   WHERE firm_id = %s AND case_id = %s ORDER BY sent_at DESC""",
                (firm_id, matter_id),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching communications: {e}")
        return []


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.post("/communications")
async def create_communication(
    body: LogCommunicationBody,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user.get("username") or str(current_user.get("id", "system"))

    if body.direction not in {"inbound", "outbound"}:
        raise HTTPException(400, "direction must be inbound or outbound")
    if body.channel not in CHANNELS:
        raise HTTPException(400, f"channel must be one of: {', '.join(CHANNELS)}")
    if body.party_type not in PARTY_TYPES:
        raise HTTPException(400, f"party_type must be one of: {', '.join(PARTY_TYPES)}")

    sent_at = body.sent_at or datetime.now(timezone.utc).isoformat()

    try:
        with get_conn(firm_id) as conn:
            # Verify claim exists
            case = conn.execute(
                "SELECT id FROM cases WHERE id = %s AND firm_id = %s",
                (body.case_id, firm_id),
            ).fetchone()
            if not case:
                raise HTTPException(404, "Claim not found")

            row = conn.execute(
                """
                INSERT INTO communications
                  (firm_id, case_id, direction, channel, party_type, party_name,
                   sender, recipient, subject, body, sent_at, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (firm_id, body.case_id, body.direction, body.channel, body.party_type,
                 body.party_name or "", body.sender or "", body.recipient or "",
                 body.subject or "", body.body or "", sent_at, user_id),
            ).fetchone()
            conn.commit()
            return {"success": True, "communication_id": row["id"], "created_at": row["created_at"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[communications] create failed: {e}")
        raise HTTPException(500, f"Failed to log communication: {e}")


@router.get("/communications")
async def list_communications(
    firm_id: str = Depends(get_current_firm_id),
    case_id: Optional[int] = None,
    party_type: Optional[str] = None,
    channel: Optional[str] = None,
    days: int = 30,
    limit: int = 100,
):
    with get_conn(firm_id) as conn:
        query = """
            SELECT id, case_id, direction, channel, party_type, party_name,
                   sender, recipient, subject, body, sent_at, created_at
            FROM communications
            WHERE firm_id = %s AND sent_at >= NOW() - INTERVAL '%s days'
        """
        params = [firm_id, days]

        if case_id is not None:
            query += " AND case_id = %s"
            params.append(case_id)
        if party_type:
            query += " AND party_type = %s"
            params.append(party_type)
        if channel:
            query += " AND channel = %s"
            params.append(channel)

        query += " ORDER BY sent_at DESC LIMIT %s"
        params.append(min(limit, 500))

        rows = conn.execute(query, params).fetchall()
    return {"success": True, "count": len(rows), "communications": [dict(r) for r in rows]}


@router.get("/cases/{case_id}/communications")
async def list_case_communications(case_id: int, firm_id: str = Depends(get_current_firm_id)):
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """
            SELECT id, direction, channel, party_type, party_name,
                   sender, recipient, subject, body, sent_at, created_at
            FROM communications
            WHERE firm_id = %s AND case_id = %s
            ORDER BY sent_at DESC
            """,
            (firm_id, case_id),
        ).fetchall()
    return {"success": True, "count": len(rows), "communications": [dict(r) for r in rows]}
