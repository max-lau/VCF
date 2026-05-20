"""
enclave_router.py
Cloud-side FastAPI router for the ParaIQ multi-tenant privilege system.
Add to main.py with: app.include_router(enclave_router, prefix="/api/privilege")

Responsibilities:
  - Maintain registry of client_id → enclave_url + api_key
  - Forward raw documents to the correct client enclave
  - Return only the screening verdict to the caller
  - Raw document text NEVER stored in the cloud DB
"""

import os
import logging
from typing import Optional, List

import httpx
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from backend.demo1.db_enclaves import (
    get_client_enclave,
    register_client_enclave,
    list_client_enclaves,
    deactivate_client_enclave,
)

logger = logging.getLogger("enclave_router")
router = APIRouter(tags=["privilege-enclave"])
security = HTTPBearer()

ADMIN_KEY = os.environ.get("PARAIQ_ADMIN_KEY", "")
ENCLAVE_TIMEOUT = 45.0   # seconds — generous for first-request model warmup


# ── Auth helpers ─────────────────────────────────────────────────────────────

def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin key required")


def get_client_id_from_request(request: Request) -> str:
    """Extract client_id from the JWT payload attached by the auth middleware."""
    client_id = getattr(request.state, "client_id", None)
    if not client_id:
        raise HTTPException(status_code=401, detail="client_id missing from token")
    return client_id


# ── Schemas ───────────────────────────────────────────────────────────────────

class ScreenPayload(BaseModel):
    doc_id:     str
    text:       str
    filename:   Optional[str]       = None
    recipients: Optional[List[str]] = []
    sender:     Optional[str]       = None
    doc_type:   Optional[str]       = "document"

class EnclaveRegistration(BaseModel):
    client_id:   str
    enclave_url: str    # e.g. "http://5.161.XX.XX:5004"
    api_key:     str
    firm_name:   Optional[str] = ""

class ReviewPayload(BaseModel):
    log_id:       str
    confirmed:    bool
    decision:     str
    notes:        Optional[str] = ""
    attorney_id:  Optional[str] = ""
    text_snippet: Optional[str] = ""


# ── Core routing logic ────────────────────────────────────────────────────────

async def _call_enclave(client_id: str, path: str, method: str = "POST", payload: dict = None) -> dict:
    """
    Generic enclave call. Raises HTTPException on failure.
    All calls use the per-client API key — no cross-client calls possible.
    """
    enclave = get_client_enclave(client_id)
    if not enclave:
        raise HTTPException(
            status_code=404,
            detail=f"No active privilege enclave for client '{client_id}'. Contact support."
        )

    url = f"{enclave['enclave_url'].rstrip('/')}/{path.lstrip('/')}"
    headers = {"X-Enclave-Key": enclave["api_key"]}

    async with httpx.AsyncClient(timeout=ENCLAVE_TIMEOUT) as client:
        try:
            if method == "POST":
                resp = await client.post(url, json=payload, headers=headers)
            elif method == "PUT":
                resp = await client.put(url, json=payload, headers=headers)
            else:
                resp = await client.get(url, headers=headers)
        except httpx.ConnectError:
            logger.error(f"Enclave unreachable for {client_id}: {url}")
            raise HTTPException(status_code=503, detail=f"Privilege enclave for {client_id} is unreachable.")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Enclave screening timed out.")

    if resp.status_code != 200:
        logger.error(f"Enclave error {resp.status_code} for {client_id}: {resp.text[:200]}")
        raise HTTPException(status_code=502, detail="Privilege enclave returned an error.")

    return resp.json()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/screen")
async def screen_document(payload: ScreenPayload, request: Request):
    """
    Called by the ingestion pipeline before any document enters the NLP stack.
    Forwards raw text to the client's enclave, returns only the verdict.

    The cloud NEVER stores the raw document text — only the verdict fields.
    """
    client_id = get_client_id_from_request(request)

    result = await _call_enclave(
        client_id=client_id,
        path="/screen",
        method="POST",
        payload=payload.model_dump(),
    )

    # Log ONLY the verdict to the cloud DB (no raw text, no document content)
    _log_verdict_to_cloud(
        client_id=client_id,
        doc_id=payload.doc_id,
        verdict=result,
    )

    return result


@router.get("/privilege-log")
async def get_privilege_log(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    only_flagged: bool = False,
    only_review_queue: bool = False,
):
    """Retrieve the privilege log from the client's enclave."""
    client_id = get_client_id_from_request(request)
    return await _call_enclave(
        client_id=client_id,
        path=f"/privilege-log?skip={skip}&limit={limit}&only_flagged={only_flagged}&only_review_queue={only_review_queue}",
        method="GET",
    )


@router.put("/review")
async def attorney_review(payload: ReviewPayload, request: Request):
    """Forward an attorney review decision to the client's enclave."""
    client_id = get_client_id_from_request(request)
    return await _call_enclave(
        client_id=client_id,
        path=f"/privilege-log/{payload.log_id}/review",
        method="PUT",
        payload=payload.model_dump(),
    )


@router.get("/stats")
async def enclave_stats(request: Request):
    """Get privilege screening stats for this client's enclave."""
    client_id = get_client_id_from_request(request)
    return await _call_enclave(client_id=client_id, path="/stats", method="GET")


@router.get("/health/{client_id}")
async def enclave_health(client_id: str, _=Depends(require_admin)):
    """Admin: check a specific client's enclave health."""
    return await _call_enclave(client_id=client_id, path="/health", method="GET")


# ── Admin endpoints (PARAIQ_ADMIN_KEY required) ────────────────────────────────

@router.post("/admin/register-enclave")
def register_enclave(payload: EnclaveRegistration, _=Depends(require_admin)):
    """
    Admin: provision a new client enclave in the registry.
    Called by provision_enclave.sh after spinning up a new VPS.
    """
    register_client_enclave(
        client_id=payload.client_id,
        enclave_url=payload.enclave_url,
        api_key=payload.api_key,
        firm_name=payload.firm_name or "",
    )
    logger.info(f"Registered enclave for {payload.client_id} at {payload.enclave_url}")
    return {"status": "registered", "client_id": payload.client_id}


@router.delete("/admin/deactivate-enclave/{client_id}")
def deactivate_enclave(client_id: str, _=Depends(require_admin)):
    deactivate_client_enclave(client_id)
    return {"status": "deactivated", "client_id": client_id}


@router.get("/admin/list-enclaves")
def list_enclaves(_=Depends(require_admin)):
    return {"enclaves": list_client_enclaves()}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _log_verdict_to_cloud(client_id: str, doc_id: str, verdict: dict):
    """
    Store ONLY the verdict in the cloud DB (no document text).
    This lets the cloud UI show privilege counts and flag status
    without ever holding privileged content.
    """
    try:
        from backend.demo1.db_enclaves import save_privilege_verdict
        save_privilege_verdict(
            client_id=client_id,
            doc_id=doc_id,
            privileged=verdict.get("privileged", False),
            privilege_type=verdict.get("privilege_type", "none"),
            confidence=verdict.get("confidence", 0.0),
            requires_review=verdict.get("requires_review", False),
            log_entry_id=verdict.get("log_entry_id", ""),
        )
    except Exception as e:
        logger.warning(f"Could not log verdict to cloud DB: {e}")
