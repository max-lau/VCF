"""
backend/demo1/ai_client.py
===========================
Centralised Anthropic client singleton.

All modules should use ``get_client()`` (sync) or ``get_async_client()``
instead of creating their own ``Anthropic(api_key=...)`` instance.
This gives us:
  - One connection pool / client instance per process
  - Consistent retry & timeout configuration
  - Centralised API-key management
"""

import os
import logging

log = logging.getLogger(__name__)

_sync_client   = None
_async_client  = None


def get_client():
    """Return a shared sync Anthropic client (created once, reused).

    If ANTHROPIC_API_KEY is not set, a client is still created with an empty
    key — the Anthropic SDK will raise a clear error at call time, matching
    the previous behaviour of per-module ``Anthropic(api_key=...)`` calls.
    """
    global _sync_client
    if _sync_client is None:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        _sync_client = anthropic.Anthropic(api_key=api_key)
        log.info("[AIClient] Initialised sync Anthropic client")
    return _sync_client


def get_async_client():
    """Return a shared async Anthropic client (created once, reused)."""
    global _async_client
    if _async_client is None:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        _async_client = anthropic.AsyncAnthropic(api_key=api_key)
        log.info("[AIClient] Initialised async Anthropic client")
    return _async_client
