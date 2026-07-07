"""
client_portal.py
================
Full client portal backend module for ParaIQ.

Token-gated (public) endpoints let a client view case status, upload
documents, download documents, and exchange messages with the firm —
all scoped by a portal access token issued via POST /grant.

Firm-only endpoints (POST /grant, DELETE /revoke) require JWT auth.

The access token maps to (firm_id, matter_id) in the
`client_portal_access` table. RLS is set with the firm_id recovered
from the token, so all downstream queries are tenant-scoped correctly.
"""
import os
import json
import secrets
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    UploadFile,
    File,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_user, get_current_firm_id


logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/client-portal", tags=["client_portal"])

# Directory for client-uploaded documents (reuses discovery upload dir)
UPLOAD_DIR = Path(
    os.environ.get(
        "DISCOVERY_UPLOAD_DIR",
        str(Path(__file__).parent.parent.parent / "uploads" / "discovery"),
    )
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# DB init — client_messages table
# ─────────────────────────────────────────────────────────────────────────────

def init_tables() -> None:
    """Create the client_messages table if it does not exist (idempotent)."""
    try:
        with get_conn("default") as conn:  # DDL — system scope
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS client_messages (
                    id            SERIAL PRIMARY KEY,
                    firm_id       TEXT NOT NULL DEFAULT 'default',
                    matter_id     INTEGER NOT NULL,
                    portal_access_id INTEGER,
                    client_name   TEXT,
                    client_email  TEXT,
                    subject       TEXT,
                    message       TEXT NOT NULL,
                    direction     TEXT NOT NULL DEFAULT 'inbound',
                    read_by_firm  BOOLEAN NOT NULL DEFAULT FALSE,
                    read_by_client BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conn.execute(
                """
                ALTER TABLE client_messages
                    DISABLE ROW LEVEL SECURITY
                """
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[client_portal] init client_messages failed: {e}")




# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class PortalAccessCreate(BaseModel):
    case_id:      int
    client_name:  str
    client_email: str
    permissions:  Optional[str] = "timeline,documents,correspondence"
    expires_days: Optional[int] = 30


class ClientMessageCreate(BaseModel):
    message: str
    subject: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: token lookup (public, bypasses RLS on client_portal_access)
# ─────────────────────────────────────────────────────────────────────────────

def _lookup_access(token: str) -> dict:
    """Look up a portal access row by token. Returns dict or raises 403."""
    with get_conn("default") as conn:  # noqa: intentional — token lookup bypasses RLS
        access = conn.execute(
            "SELECT * FROM client_portal_access WHERE access_token = %s AND is_active = TRUE",
            (token,),
        ).fetchone()
        if not access:
            raise HTTPException(403, "Invalid or expired portal link")
        a = dict(access)
        if a.get("expires_at") and str(a["expires_at"]) < datetime.now().isoformat():
            raise HTTPException(403, "Portal link has expired")
        # bump last_accessed
        conn.execute(
            "UPDATE client_portal_access SET last_accessed = %s WHERE id = %s",
            (datetime.now().isoformat(), a["id"]),
        )
    return a


# ─────────────────────────────────────────────────────────────────────────────
# 1. POST /grant — firm issues a portal access token (auth required)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/grant")
def grant_portal_access(
    body:    PortalAccessCreate,
    firm_id: str = Depends(get_current_firm_id),
):
    """Firm generates a portal access token for a client.

    Body: {case_id, client_name, client_email, expires_days}
    Returns the new access record + portal_url.
    """
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=body.expires_days or 30)).isoformat()
    with get_conn(firm_id) as conn:
        cur = conn.execute(
            """
            INSERT INTO client_portal_access
              (firm_id, matter_id, client_name, client_email,
               access_token, permissions, expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (firm_id, body.case_id, body.client_name, body.client_email,
             token, body.permissions, expires),
        )
        new_id = cur.fetchone()["id"]
        row = conn.execute(
            "SELECT * FROM client_portal_access WHERE id = %s", (new_id,)
        ).fetchone()
    return {**dict(row), "portal_url": f"/client-portal/view/{token}"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. GET /view/{token} — public portal access info (token-gated)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/view/{token}")
def view_portal(token: str):
    """Returns portal access info: firm name, case info, client name."""
    a = _lookup_access(token)

    matter_id = a["matter_id"]
    portal_firm = a.get("firm_id", "default")
    perms = set((a.get("permissions") or "").split(","))
    payload = {"access": a, "matter": {}}

    with get_conn(portal_firm) as conn:
        case = conn.execute(
            "SELECT id, client_name, case_number, status, created_at FROM cases WHERE id = %s",
            (matter_id,),
        ).fetchone()
        if case:
            payload["matter"] = dict(case)

        if "documents" in perms:
            rows = conn.execute(
                "SELECT id, document_name, source, upload_date FROM case_documents WHERE case_id = %s",
                (matter_id,),
            ).fetchall()
            payload["documents"] = [dict(r) for r in rows]

        if "correspondence" in perms:
            rows = conn.execute(
                "SELECT id, subject, date, direction, from_party, to_party FROM correspondence WHERE matter_id = %s",
                (matter_id,),
            ).fetchall()
            payload["correspondence"] = [dict(r) for r in rows]

        if "timeline" in perms:
            try:
                docs = conn.execute(
                    "SELECT events_json FROM case_documents WHERE case_id = %s",
                    (matter_id,),
                ).fetchall()
                all_events: List = []
                for d in docs:
                    ev_json = dict(d).get("events_json")
                    if ev_json:
                        try:
                            items = ev_json if isinstance(ev_json, list) else json.loads(ev_json)
                            all_events.extend(items[:5])
                        except (json.JSONDecodeError, KeyError, TypeError):
                            pass
                payload["timeline"] = all_events[:20]
            except (KeyError, TypeError, ValueError):
                payload["timeline"] = []

    return payload


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET /cases/{token} — case details + deadlines + recent documents
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/cases/{token}")
def get_case_details(token: str):
    """Returns case details, status, upcoming deadlines, and recent documents."""
    a = _lookup_access(token)
    matter_id = a["matter_id"]
    portal_firm = a.get("firm_id", "default")

    with get_conn(portal_firm) as conn:
        case = conn.execute(
            "SELECT * FROM cases WHERE id = %s AND deleted = FALSE",
            (matter_id,),
        ).fetchone()
        if not case:
            raise HTTPException(404, "Case not found")
        case_dict = dict(case)

        # Upcoming deadlines from calendar_events
        deadlines: List = []
        try:
            rows = conn.execute(
                """
                SELECT id, title, event_date, event_type, description
                FROM calendar_events
                WHERE matter_id = %s
                  AND event_date IS NOT NULL
                ORDER BY event_date ASC
                """,
                (matter_id,),
            ).fetchall()
            now_iso = datetime.now().isoformat()
            deadlines = [
                dict(r) for r in rows
                if r.get("event_date") and str(r["event_date"]) >= now_iso
            ]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[client_portal] deadlines fetch failed: {e}")

        # Recent documents
        recent_docs: List = []
        try:
            rows = conn.execute(
                """
                SELECT id, document_name, source, upload_date
                FROM case_documents
                WHERE case_id = %s
                ORDER BY upload_date DESC NULLS LAST
                LIMIT 10
                """,
                (matter_id,),
            ).fetchall()
            recent_docs = [dict(r) for r in rows]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[client_portal] recent docs fetch failed: {e}")

    return {
        "case": case_dict,
        "status": case_dict.get("status"),
        "upcoming_deadlines": deadlines,
        "recent_documents": recent_docs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. POST /upload/{token} — client uploads a document
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/upload/{token}")
async def upload_document(token: str, file: UploadFile = File(...)):
    """Client uploads a document. Saved to DISCOVERY_UPLOAD_DIR and a
    case_documents record is created. Returns doc_id."""
    a = _lookup_access(token)
    matter_id = a["matter_id"]
    portal_firm = a.get("firm_id", "default")

    if not file or not file.filename:
        raise HTTPException(400, "No file provided")

    # Read file bytes
    contents = await file.read()
    if not contents:
        raise HTTPException(400, "Empty file")

    # Build a safe, unique filename
    safe_name = f"{secrets.token_hex(4)}_{Path(file.filename).name}"
    dest = UPLOAD_DIR / safe_name
    try:
        dest.write_bytes(contents)
    except OSError as e:
        logger.error(f"[client_portal] failed to write upload {safe_name}: {e}")
        raise HTTPException(500, "Failed to save uploaded file")

    # Extract text (best-effort): try utf-8 decode for text-like files
    doc_text = ""
    try:
        doc_text = contents.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        doc_text = ""

    source_path = str(dest)

    with get_conn(portal_firm) as conn:
        cur = conn.execute(
            """
            INSERT INTO case_documents (case_id, document_name, source, doc_text)
            VALUES (%s,%s,%s,%s)
            RETURNING id
            """,
            (matter_id, file.filename, source_path, doc_text),
        )
        doc_id = cur.fetchone()["id"]

    return {"doc_id": doc_id, "filename": file.filename, "saved_as": safe_name}


# ─────────────────────────────────────────────────────────────────────────────
# 5. GET /documents/{token} — list documents visible to the client
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/documents/{token}")
def list_documents(token: str):
    """List case_documents where case_id matches the portal's matter_id."""
    a = _lookup_access(token)
    matter_id = a["matter_id"]
    portal_firm = a.get("firm_id", "default")

    with get_conn(portal_firm) as conn:
        rows = conn.execute(
            """
            SELECT id, document_name, source, upload_date
            FROM case_documents
            WHERE case_id = %s
            ORDER BY upload_date DESC NULLS LAST
            """,
            (matter_id,),
        ).fetchall()
    return {"documents": [dict(r) for r in rows]}


# ─────────────────────────────────────────────────────────────────────────────
# 6. GET /documents/{token}/{doc_id} — download/view a document's text
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/documents/{token}/{doc_id}")
def get_document(token: str, doc_id: int):
    """Download/view a specific document's text (scoped to the portal case)."""
    a = _lookup_access(token)
    matter_id = a["matter_id"]
    portal_firm = a.get("firm_id", "default")

    with get_conn(portal_firm) as conn:
        row = conn.execute(
            """
            SELECT id, case_id, document_name, source, doc_text, upload_date
            FROM case_documents
            WHERE id = %s AND case_id = %s
            """,
            (doc_id, matter_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Document not found or not accessible")
        doc = dict(row)

    # Return the document text plus metadata
    return {
        "doc_id": doc["id"],
        "filename": doc.get("document_name"),
        "source": doc.get("source"),
        "upload_date": doc.get("upload_date"),
        "text": doc.get("doc_text") or "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. POST /message/{token} — client sends a message to the firm
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/message/{token}")
def send_message(token: str, body: ClientMessageCreate):
    """Client sends a message to the firm. Stored in client_messages."""
    a = _lookup_access(token)
    matter_id = a["matter_id"]
    portal_firm = a.get("firm_id", "default")

    with get_conn("default") as conn:  # client_messages has RLS disabled
        cur = conn.execute(
            """
            INSERT INTO client_messages
              (firm_id, matter_id, portal_access_id, client_name, client_email,
               subject, message, direction, read_by_firm, read_by_client)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                portal_firm,
                matter_id,
                a.get("id"),
                a.get("client_name"),
                a.get("client_email"),
                body.subject,
                body.message,
                "inbound",
                False,
                True,
            ),
        )
        msg_id = cur.fetchone()["id"]

    return {"message_id": msg_id, "status": "sent"}


# ─────────────────────────────────────────────────────────────────────────────
# 8. GET /messages/{token} — list messages between client and firm
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/messages/{token}")
def list_messages(token: str):
    """List messages between client and firm (both directions)."""
    a = _lookup_access(token)
    matter_id = a["matter_id"]
    portal_firm = a.get("firm_id", "default")

    with get_conn("default") as conn:  # client_messages has RLS disabled
        rows = conn.execute(
            """
            SELECT id, subject, message, direction,
                   read_by_firm, read_by_client, created_at
            FROM client_messages
            WHERE firm_id = %s AND matter_id = %s
            ORDER BY created_at ASC
            """,
            (portal_firm, matter_id),
        ).fetchall()

    return {"messages": [dict(r) for r in rows]}


# ─────────────────────────────────────────────────────────────────────────────
# 9. DELETE /revoke/{token} — firm revokes portal access (auth required)
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/revoke/{token}")
def revoke_portal_access(
    token:    str,
    firm_id:  str = Depends(get_current_firm_id),
    user:     dict = Depends(get_current_user),
):
    """Firm revokes a portal access token. Requires JWT auth."""
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT id, firm_id FROM client_portal_access WHERE access_token = %s",
            (token,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Portal access token not found")
        if dict(row).get("firm_id") != firm_id:
            raise HTTPException(403, "Not authorized to revoke this portal access")
        conn.execute(
            "UPDATE client_portal_access SET is_active = FALSE WHERE id = %s",
            (row["id"],),
        )
    return {"revoked": token, "access_id": row["id"]}


# ── Firm-side management routes (Option B consolidation: client_portal.py is canonical) ──
# Ported from routers/misc_routers.py so this router is a superset serving both
# ClientPortalManageView (grants/grant/revoke-by-token) and ClientPortalView
# (matter/{id}/accesses, access/{id}). Resolves the dead-code mount from the
# duplicate client_portal_router import in main.py.

@router.get("/grants")
def list_all_grants(firm_id: str = Depends(get_current_firm_id)):
    """Firm-wide list of all portal accesses. Consumed by ClientPortalManageView.vue."""
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """
            SELECT id, matter_id, client_name, client_email, permissions,
                   access_token, expires_at, last_accessed, is_active, created_at
            FROM client_portal_access
            WHERE firm_id = %s ORDER BY created_at DESC
            """,
            (firm_id,),
        ).fetchall()
    return {"grants": [dict(r) for r in rows]}


@router.get("/matter/{matter_id}/accesses")
def list_matter_accesses(matter_id: int, firm_id: str = Depends(get_current_firm_id)):
    """Per-matter access list. Consumed by ClientPortalView.vue."""
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """
            SELECT id, client_name, client_email, permissions,
                   expires_at, last_accessed, is_active, created_at, access_token
            FROM client_portal_access
            WHERE matter_id = %s ORDER BY created_at DESC
            """,
            (matter_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.delete("/access/{access_id}")
def revoke_access_by_id(access_id: int, firm_id: str = Depends(get_current_firm_id)):
    """Revoke by numeric id (ownership-scoped). Consumed by ClientPortalView.vue."""
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT id, firm_id FROM client_portal_access WHERE id = %s",
            (access_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Portal access not found")
        if dict(row).get("firm_id") != firm_id:
            raise HTTPException(403, "Not authorized to revoke this portal access")
        conn.execute(
            "UPDATE client_portal_access SET is_active = FALSE WHERE id = %s",
            (access_id,),
        )
    return {"revoked": access_id}
