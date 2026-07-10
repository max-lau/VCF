# -----------------------------------------------------------------------------
# Drop-in additions/replacements for backend/demo1/auth.py
#
# Replaces: getattr(request.state, "firm_id", "default")
# With: two explicit, non-overlapping trust paths that fail closed.
#
# Wire get_current_firm_id onto every browser-facing route (this is almost
# certainly what most of the 109 call sites should become).
# Wire get_m2m_firm_id ONLY onto the 3 M2M paths:
#   /intake/scan, /discovery/process/ocr/, /media/transcribe/discovery/
# -----------------------------------------------------------------------------

import logging
from fastapi import Depends, Header, HTTPException, Request

logger = logging.getLogger("paraiq.auth.firm_id")

# Adjust import to wherever your JWT decode + pg pool helpers live.
# from .auth import decode_jwt  # existing JWT decode, unchanged
# from .pg import get_pool


# -----------------------------------------------------------------------------
# 1. Browser / JWT path — the ONLY canonical way browser traffic gets firm_id.
#    Never defaults. Never reads request.state directly as a fallback.
# -----------------------------------------------------------------------------
async def get_current_firm_id(request: Request) -> str:
    """
    Resolves firm_id strictly from a decoded JWT. No fallback, ever.
    Use this dependency on every route reachable by a logged-in browser user.
    """
    user = getattr(request.state, "user", None)  # set by your existing JWT middleware
    firm_id = getattr(user, "firm_id", None) if user else None

    if not firm_id:
        logger.warning(
            "firm_id resolution failed on JWT path: path=%s user_present=%s",
            request.url.path,
            user is not None,
        )
        raise HTTPException(status_code=401, detail="Unable to resolve firm context")

    return firm_id


# -----------------------------------------------------------------------------
# 2. M2M / API-key path — the ONLY three routes that should ever use this.
#    Caller must supply firm_id explicitly (header or query param — pick one
#    convention and use it everywhere for consistency; header shown here).
#    Validated against a real row in `firms`, not just "non-empty string".
# -----------------------------------------------------------------------------
async def get_m2m_firm_id(
    request: Request,
    x_firm_id: str | None = Header(default=None, alias="X-Firm-Id"),
) -> str:
    """
    Resolves firm_id for internal M2M callers (pollers, schedulers) that
    authenticate via the static API key and have no JWT. The caller already
    knows which firm it's acting on behalf of — it must say so explicitly.
    """
    if not x_firm_id:
        logger.warning(
            "M2M call missing X-Firm-Id: path=%s caller=%s",
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=400, detail="X-Firm-Id header is required")

    # Validate against a real row — never trust the string as-is.
    # Replace with your actual pg.py pool/context helper.
    from .pg import get_pool  # local import to avoid circulars; adjust as needed

    pool = get_pool()
    async with pool.acquire() as conn:
        # IMPORTANT: this lookup itself must not require tenant RLS context
        # to already be set (same chicken-and-egg class of problem migration
        # 009 solved for client_portal_access). If `firms` is RLS-protected,
        # this query needs its own narrow, safe SELECT policy — check before
        # wiring this in.
        row = await conn.fetchrow("SELECT id FROM firms WHERE id = $1", x_firm_id)

    if row is None:
        logger.warning(
            "M2M call with unresolvable firm_id: path=%s firm_id=%s",
            request.url.path,
            x_firm_id,
        )
        raise HTTPException(status_code=400, detail="Unknown firm_id")

    return x_firm_id


# -----------------------------------------------------------------------------
# 3. TRIPWIRE — deploy this FIRST, before touching any of the 109 call sites.
#    Drop-in replacement for the old getattr(...) pattern. Behavior is
#    UNCHANGED (still defaults to "default"), but every fallback is now
#    logged loudly with enough context to build a real map of which of the
#    109 sites actually fire in production, and from whom.
#
#    Run this for a day or two of real traffic. Anything that logs is either
#    (a) legitimately one of the 3 M2M paths — migrate to get_m2m_firm_id, or
#    (b) a bug/forgotten caller — investigate before deciding how to migrate it.
# -----------------------------------------------------------------------------
def firm_id_with_tripwire(request: Request, call_site: str) -> str:
    """
    Temporary. Use as: firm_id_with_tripwire(request, "privilege_log.py:get_stats")
    Delete once the full migration to get_current_firm_id/get_m2m_firm_id lands.
    """
    firm_id = getattr(request.state, "firm_id", None)
    if firm_id is None:
        logger.warning(
            "FIRM_ID_FALLBACK_HIT call_site=%s path=%s method=%s client=%s auth_header_present=%s",
            call_site,
            request.url.path,
            request.method,
            request.client.host if request.client else "unknown",
            "authorization" in request.headers,
        )
        firm_id = "default"
    return firm_id
