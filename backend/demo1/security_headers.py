"""
security_headers.py
==================
ParaIQ Security Headers Middleware (#9)

Adds OWASP-recommended security headers to every HTTP response:
  - Content-Security-Policy: restricts resource origins
  - Strict-Transport-Security: enforces HTTPS
  - X-Frame-Options: clickjacking defense
  - X-Content-Type-Options: MIME-type sniffing prevention
  - Referrer-Policy: controls referrer information leakage
  - Permissions-Policy: disables unused browser features
  - X-DNS-Prefetch-Control: disables DNS prefetching
  - Cross-Origin-Opener-Policy: process isolation

Usage in main.py:
    from backend.demo1.security_headers import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
"""

import os
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ── Configurable CSP directives ───────────────────────────────────────────────

_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https://api.anthropic.com https://cloud.langfuse.com; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'; "
    "object-src 'none'"
)

# ── Headers applied to every response ─────────────────────────────────────────

_SECURITY_HEADERS = {
    "X-Content-Type-Options":    "nosniff",
    "X-Frame-Options":           "DENY",
    "X-DNS-Prefetch-Control":    "off",
    "Referrer-Policy":           "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy":        (
        "geolocation=(), microphone=(), camera=(), "
        "payment=(), usb=(), magnetometer=(), gyroscope=()"
    ),
}

# HSTS: only enable when served over HTTPS (or behind a proxy that terminates TLS)
_HSTS_HEADER = "max-age=63072000; includeSubDomains; preload"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects security headers into every HTTP response.
    Placed outermost in the middleware stack so headers are set even on
    error responses (500s, 401s, etc.).
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # --- Content-Security-Policy ---
        csp = os.getenv("PARAIQ_CSP", _DEFAULT_CSP)
        response.headers["Content-Security-Policy"] = csp

        # --- HSTS (only for HTTPS or when behind a TLS-terminating proxy) ---
        # Check X-Forwarded-Proto for proxy scenarios, or is_https flag
        is_https = (
            request.url.scheme == "https"
            or request.headers.get("X-Forwarded-Proto", "") == "https"
            or os.getenv("PARAIQ_FORCE_HTTPS", "").lower() in ("1", "true", "yes")
        )
        if is_https:
            response.headers["Strict-Transport-Security"] = _HSTS_HEADER

        # --- Static security headers ---
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)

        return response


def init_security_headers():
    """Called at startup to confirm middleware is wired."""
    logger.info("[SecurityHeaders] Middleware initialized ✓")
    print("[SecurityHeaders] Middleware initialized ✓")
