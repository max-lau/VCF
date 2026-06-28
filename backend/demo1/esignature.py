"""
esignature.py
==============
ParaIQ — E-signature integration with DocuSign API + email-based fallback.

Three modes:
1. DocuSign API (if DOCUSIGN_* env vars set) — full e-signature workflow
2. Email-based fallback — sends signing links via email with token-gated page
3. Internal signature — attorney signs/approves within ParaIQ

Endpoints:
  POST /esign/send          — Create signature request (DocuSign or email)
  GET  /esign/requests       — List all signature requests for the firm
  GET  /esign/requests/{id}  — Get status of a specific request
  GET  /esign/sign/{token}   — Public signing page (token-gated, no auth)
  POST /esign/sign/{token}   — Submit a signature (public, token-gated)
  POST /esign/cancel/{id}    — Cancel a signature request
  GET  /esign/webhook        — DocuSign webhook callback (connect integration)
"""
import os
import json
import logging
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import RedirectResponse, PlainTextResponse
from pydantic import BaseModel, EmailStr

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_user, get_current_firm_id

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────

DOCUSIGN_CLIENT_ID     = os.getenv("DOCUSIGN_CLIENT_ID", "")
DOCUSIGN_CLIENT_SECRET = os.getenv("DOCUSIGN_CLIENT_SECRET", "")
DOCUSIGN_ACCOUNT_ID    = os.getenv("DOCUSIGN_ACCOUNT_ID", "")
DOCUSIGN_BASE_URL      = os.getenv("DOCUSIGN_BASE_URL", "https://account.docusign.com")
DOCUSIGN_API_URL       = os.getenv("DOCUSIGN_API_URL", "https://demo.docusign.net/restapi")
DOCUSIGN_REDIRECT_URI  = os.getenv("DOCUSIGN_REDIRECT_URI", "")

DOCUSIGN_ENABLED = bool(DOCUSIGN_CLIENT_ID and DOCUSIGN_CLIENT_SECRET and DOCUSIGN_ACCOUNT_ID)


def _row_to_dict(row) -> Dict[str, Any]:
    return dict(row) if hasattr(row, "keys") else dict(row._mapping)


# ── Models ────────────────────────────────────────────────────────────────────

class SignerModel(BaseModel):
    name:  str
    email: EmailStr
    role:  Optional[str] = "signer"  # signer, cc, approver


class SignatureRequestCreate(BaseModel):
    document_name: str
    document_text: Optional[str] = None       # text content for email fallback
    document_id:   Optional[int] = None       # case_documents.id
    case_id:       Optional[int] = None
    subject:       Optional[str] = None
    message:       Optional[str] = None
    signers:       List[SignerModel]
    expires_days:  Optional[int] = 30
    provider:      Optional[str] = None       # "docusign", "email", "internal" — auto-detected if None


class InternalSignModel(BaseModel):
    request_id: int
    signer_name: str
    signature_text: str  # typed signature (e.g., "/s/ John Smith")
    signature_image: Optional[str] = None  # base64 data URL from canvas


# ── Table Init ────────────────────────────────────────────────────────────────

def init_esign_tables():
    """Create esignature tables if they don't exist."""
    try:
        with get_conn("default") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS esign_requests (
                    id SERIAL PRIMARY KEY,
                    firm_id TEXT NOT NULL,
                    case_id INT,
                    document_name TEXT NOT NULL,
                    document_id INT,
                    document_text TEXT,
                    subject TEXT,
                    message TEXT,
                    provider TEXT NOT NULL DEFAULT 'email',
                    status TEXT NOT NULL DEFAULT 'pending',
                    docusign_envelope_id TEXT,
                    expires_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    metadata JSONB DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS esign_signers (
                    id SERIAL PRIMARY KEY,
                    request_id INT NOT NULL REFERENCES esign_requests(id) ON DELETE CASCADE,
                    firm_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'signer',
                    status TEXT NOT NULL DEFAULT 'pending',
                    sign_token TEXT UNIQUE,
                    signed_at TIMESTAMPTZ,
                    signature_text TEXT,
                    signature_image TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            conn.commit()
    except Exception as e:
        logger.warning(f"[Esign] Table init skipped: {e}")


init_esign_tables()


# ── DocuSign Helpers ──────────────────────────────────────────────────────────

_DOCUSIGN_TOKEN: Optional[dict] = None
_DOCUSIGN_TOKEN_EXPIRES: datetime = datetime.min


async def _get_docusign_token() -> str:
    """Get a valid DocuSign access token (refreshes if expired)."""
    global _DOCUSIGN_TOKEN, _DOCUSIGN_TOKEN_EXPIRES

    if _DOCUSIGN_TOKEN and datetime.now(timezone.utc) < _DOCUSIGN_TOKEN_EXPIRES:
        return _DOCUSIGN_TOKEN.get("access_token", "")

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{DOCUSIGN_BASE_URL}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": DOCUSIGN_CLIENT_ID,
                "client_secret": DOCUSIGN_CLIENT_SECRET,
                "scope": "signature impersonation",
            },
            timeout=15
        )
        resp.raise_for_status()
        _DOCUSIGN_TOKEN = resp.json()
        _DOCUSIGN_TOKEN_EXPIRES = datetime.now(timezone.utc) + datetime.timedelta(
            seconds=_DOCUSIGN_TOKEN.get("expires_in", 3600) - 60
        )
        return _DOCUSIGN_TOKEN["access_token"]


async def _create_docusign_envelope(req: SignatureRequestCreate, firm_id: str) -> Dict:
    """Create a DocuSign envelope and return envelope_id + signing URLs."""
    token = await _get_docusign_token()

    # Build envelope definition
    envelope = {
        "emailSubject": req.subject or f"Please sign: {req.document_name}",
        "emailBlurb": req.message or "Please review and sign the attached document.",
        "status": "sent",
        "documents": [],
        "recipients": {"signers": [], "carbonCopies": []},
    }

    # Add document — if we have text, create an inline document
    if req.document_text:
        envelope["documents"].append({
            "documentBase64": req.document_text.encode().hex(),  # simplified
            "name": req.document_name,
            "fileExtension": "txt",
            "documentId": "1",
        })
    elif req.document_id:
        # Fetch from case_documents
        try:
            with get_conn(firm_id) as conn:
                row = conn.execute(
                    "SELECT doc_text FROM case_documents WHERE id = %s AND firm_id = %s",
                    (req.document_id, firm_id)
                ).fetchone()
                if row and row["doc_text"]:
                    envelope["documents"].append({
                        "documentBase64": row["doc_text"].encode().hex(),
                        "name": req.document_name,
                        "fileExtension": "txt",
                        "documentId": "1",
                    })
        except Exception as e:
            logger.error(f"[Esign] Failed to fetch document: {e}")

    # Add signers
    for i, signer in enumerate(req.signers):
        if signer.role == "cc":
            envelope["recipients"]["carbonCopies"].append({
                "email": signer.email,
                "name": signer.name,
                "recipientId": str(i + 1),
            })
        else:
            envelope["recipients"]["signers"].append({
                "email": signer.email,
                "name": signer.name,
                "recipientId": str(i + 1),
                "routingOrder": str(i + 1),
                "tabs": {
                    "signHereTabs": [{
                        "anchorString": "/s/",
                        "anchorYOffset": "10",
                        "anchorXOffset": "20",
                    }]
                },
            })

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{DOCUSIGN_API_URL}/v2.1/accounts/{DOCUSIGN_ACCOUNT_ID}/envelopes",
            json=envelope,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30
        )

        if resp.status_code == 201:
            result = resp.json()
            return {
                "envelope_id": result.get("envelopeId", ""),
                "status": "sent",
                "provider": "docusign",
            }
        else:
            logger.error(f"[Esign] DocuSign error: {resp.status_code} {resp.text}")
            raise HTTPException(502, f"DocuSign API error: {resp.status_code}")


# ── Email Fallback ────────────────────────────────────────────────────────────

def _generate_sign_token() -> str:
    """Generate a secure, unique signing token."""
    return secrets.token_urlsafe(32)


async def _send_email_fallback(req: SignatureRequestCreate, request_id: int, firm_id: str, base_url: str):
    """Send signing invitation emails with token-gated links (fallback when DocuSign not configured)."""
    # In production, this would use the existing email infrastructure
    # (SMTP config from env vars). For now, we store the tokens and
    # the frontend exposes the signing URLs.
    try:
        with get_conn(firm_id) as conn:
            for signer in req.signers:
                token = _generate_sign_token()
                conn.execute(
                    """
                    INSERT INTO esign_signers (request_id, firm_id, name, email, role, sign_token, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                    """,
                    (request_id, firm_id, signer.name, signer.email, signer.role, token)
                )
            conn.commit()

            # Build signing URLs
            signers_data = conn.execute(
                "SELECT id, name, email, sign_token FROM esign_signers WHERE request_id = %s",
                (request_id,)
            ).fetchall()

        urls = []
        for s in signers_data:
            url = f"{base_url}/esign/sign/{s['sign_token']}"
            urls.append({"name": s["name"], "email": s["email"], "url": url})

        # TODO: Send actual emails via SMTP when configured
        # For now, return the URLs so the frontend can display/share them
        logger.info(f"[Esign] Email fallback: {len(urls)} signing URLs generated for request {request_id}")
        return urls

    except Exception as e:
        logger.error(f"[Esign] Email fallback failed: {e}")
        raise


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/send")
async def send_signature_request(
    req: SignatureRequestCreate,
    request: Request,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a signature request.

    Auto-detects provider:
    - DocuSign if DOCUSIGN_* env vars are configured
    - Email fallback otherwise (generates token-gated signing URLs)
    """
    if not req.signers:
        raise HTTPException(400, "At least one signer is required")

    provider = req.provider
    if not provider:
        provider = "docusign" if DOCUSIGN_ENABLED else "email"

    expires_at = datetime.now(timezone.utc) + datetime.timedelta(days=req.expires_days or 30)

    # Create request record
    try:
        with get_conn(firm_id) as conn:
            cur = conn.execute(
                """
                INSERT INTO esign_requests
                  (firm_id, case_id, document_name, document_id, document_text,
                   subject, message, provider, status, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                RETURNING id
                """,
                (firm_id, req.case_id, req.document_name, req.document_id,
                 req.document_text, req.subject, req.message, provider, expires_at)
            )
            request_id = cur.fetchone()["id"]
            conn.commit()
    except Exception as e:
        logger.error(f"[Esign] Failed to create request: {e}")
        raise HTTPException(500, "Failed to create signature request")

    base_url = str(request.base_url).rstrip("/")

    if provider == "docusign" and DOCUSIGN_ENABLED:
        try:
            ds_result = await _create_docusign_envelope(req, firm_id)
            with get_conn(firm_id) as conn:
                conn.execute(
                    "UPDATE esign_requests SET docusign_envelope_id = %s, status = 'sent' WHERE id = %s",
                    (ds_result["envelope_id"], request_id)
                )
                conn.commit()

            # Still create local signer records for tracking
            await _send_email_fallback(req, request_id, firm_id, base_url)

            return {
                "request_id": request_id,
                "provider": "docusign",
                "envelope_id": ds_result["envelope_id"],
                "status": "sent",
                "signers": req.signers,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[Esign] DocuSign failed, falling back to email: {e}")
            # Fall through to email
            with get_conn(firm_id) as conn:
                conn.execute(
                    "UPDATE esign_requests SET provider = 'email' WHERE id = %s",
                    (request_id,)
                )
                conn.commit()

    # Email fallback
    sign_urls = await _send_email_fallback(req, request_id, firm_id, base_url)

    return {
        "request_id": request_id,
        "provider": "email",
        "status": "pending",
        "signers": sign_urls,
        "message": "Signing invitations created. Share the URLs with signers or configure DocuSign for automatic email delivery.",
    }


@router.get("/requests")
async def list_requests(
    status: Optional[str] = None,
    case_id: Optional[int] = None,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """List all signature requests for the firm."""
    try:
        with get_conn(firm_id) as conn:
            sql = """
                SELECT r.id, r.case_id, r.document_name, r.subject, r.provider,
                       r.status, r.expires_at, r.created_at, r.completed_at,
                       r.docusign_envelope_id,
                       (SELECT COUNT(*) FROM esign_signers s WHERE s.request_id = r.id) AS total_signers,
                       (SELECT COUNT(*) FROM esign_signers s WHERE s.request_id = r.id AND s.status = 'signed') AS signed_count
                FROM esign_requests r
                WHERE r.firm_id = %s
            """
            params = [firm_id]
            if status:
                sql += " AND r.status = %s"
                params.append(status)
            if case_id:
                sql += " AND r.case_id = %s"
                params.append(case_id)
            sql += " ORDER BY r.created_at DESC"

            rows = conn.execute(sql, params).fetchall()
            return {"requests": [_row_to_dict(r) for r in rows]} if rows else {"requests": []}
    except Exception as e:
        logger.error(f"[Esign] List failed: {e}")
        raise HTTPException(500, "Failed to list signature requests")


@router.get("/requests/{request_id}")
async def get_request(
    request_id: int,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Get detailed status of a signature request including per-signer status."""
    try:
        with get_conn(firm_id) as conn:
            req_row = conn.execute(
                "SELECT * FROM esign_requests WHERE id = %s AND firm_id = %s",
                (request_id, firm_id)
            ).fetchone()
            if not req_row:
                raise HTTPException(404, "Signature request not found")

            signers = conn.execute(
                "SELECT id, name, email, role, status, signed_at, sign_token FROM esign_signers WHERE request_id = %s ORDER BY id",
                (request_id,)
            ).fetchall()

            result = _row_to_dict(req_row)
            result["signers"] = [_row_to_dict(s) for s in signers]
            # Don't expose tokens in the detail view
            for s in result["signers"]:
                s.pop("sign_token", None)
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Esign] Get request failed: {e}")
        raise HTTPException(500, "Failed to get request details")


@router.get("/sign/{token}")
async def get_sign_page(
    token: str,
):
    """Public signing page — token-gated, no auth required. Returns signer info."""
    try:
        with get_conn("default") as conn:
            signer = conn.execute(
                """
                SELECT s.id, s.name, s.email, s.role, s.status, s.signed_at,
                       r.document_name, r.document_text, r.subject, r.message,
                       r.expires_at, r.case_id, r.firm_id
                FROM esign_signers s
                JOIN esign_requests r ON r.id = s.request_id
                WHERE s.sign_token = %s
                """,
                (token,)
            ).fetchone()

            if not signer:
                raise HTTPException(404, "Invalid or expired signing link")

            s = _row_to_dict(signer)
            if s["status"] == "signed":
                return {
                    "status": "already_signed",
                    "signer_name": s["name"],
                    "signed_at": s["signed_at"],
                    "document_name": s["document_name"],
                }

            if s["expires_at"] and datetime.now(timezone.utc) > s["expires_at"].replace(tzinfo=timezone.utc):
                return {
                    "status": "expired",
                    "signer_name": s["name"],
                    "document_name": s["document_name"],
                }

            return {
                "status": "ready",
                "signer_name": s["name"],
                "signer_email": s["email"],
                "document_name": s["document_name"],
                "document_text": s["document_text"],
                "subject": s.get("subject"),
                "message": s.get("message"),
                "token": token,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Esign] Sign page failed: {e}")
        raise HTTPException(500, "Failed to load signing page")


@router.post("/sign/{token}")
async def submit_signature(
    token: str,
    sig: InternalSignModel,
    request: Request,
):
    """Submit a signature via the public signing page."""
    try:
        with get_conn("default") as conn:
            signer = conn.execute(
                "SELECT id, name, status, request_id, firm_id FROM esign_signers WHERE sign_token = %s",
                (token,)
            ).fetchone()

            if not signer:
                raise HTTPException(404, "Invalid signing token")
            if signer["status"] == "signed":
                raise HTTPException(400, "Document already signed")

            # Capture signature metadata
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            now = datetime.now(timezone.utc)
            conn.execute(
                """
                UPDATE esign_signers
                SET status = 'signed', signed_at = %s,
                    signature_text = %s, signature_image = %s,
                    ip_address = %s, user_agent = %s
                WHERE id = %s
                """,
                (now, sig.signature_text, sig.signature_image, client_ip, user_agent, signer["id"])
            )

            # Check if all signers have signed
            all_signers = conn.execute(
                "SELECT status FROM esign_signers WHERE request_id = %s",
                (signer["request_id"],)
            ).fetchall()
            all_signed = all(s["status"] == "signed" for s in all_signers)

            if all_signed:
                conn.execute(
                    "UPDATE esign_requests SET status = 'completed', completed_at = %s WHERE id = %s",
                    (now, signer["request_id"])
                )

            conn.commit()

            return {
                "status": "signed",
                "signer_name": signer["name"],
                "all_signed": all_signed,
                "signed_at": now.isoformat(),
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Esign] Submit signature failed: {e}")
        raise HTTPException(500, "Failed to submit signature")


@router.post("/cancel/{request_id}")
async def cancel_request(
    request_id: int,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Cancel a pending signature request."""
    try:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                "SELECT id, status FROM esign_requests WHERE id = %s AND firm_id = %s",
                (request_id, firm_id)
            ).fetchone()
            if not row:
                raise HTTPException(404, "Request not found")
            if row["status"] in ("completed", "cancelled"):
                raise HTTPException(400, f"Cannot cancel a {row['status']} request")

            conn.execute(
                "UPDATE esign_requests SET status = 'cancelled' WHERE id = %s",
                (request_id,)
            )
            conn.commit()
            return {"cancelled": request_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Esign] Cancel failed: {e}")
        raise HTTPException(500, "Failed to cancel request")


@router.post("/webhook")
async def docusign_webhook(request: Request):
    """DocuSign Connect webhook — receives status updates."""
    try:
        body = await request.body()
        # In production, verify the webhook signature
        data = json.loads(body)

        envelope_id = data.get("envelopeId")
        status = data.get("status", "").lower()

        if envelope_id and status:
            with get_conn("default") as conn:
                if status == "completed":
                    conn.execute(
                        "UPDATE esign_requests SET status = 'completed', completed_at = NOW() WHERE docusign_envelope_id = %s",
                        (envelope_id,)
                    )
                elif status in ("declined", "voided"):
                    conn.execute(
                        "UPDATE esign_requests SET status = %s WHERE docusign_envelope_id = %s",
                        (status, envelope_id)
                    )
                conn.commit()

        return {"received": True}
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"[Esign] Webhook parse error: {e}")
        return {"received": False, "error": str(e)}
