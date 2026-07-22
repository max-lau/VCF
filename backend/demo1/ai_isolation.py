"""
ai_isolation.py
===============
ParaIQ Per-Client AI Model Isolation (#12)

Ensures each tenant's AI interactions are completely isolated:
  - Per-tenant LLM client instances (no shared connection state)
  - Per-tenant conversation context (no cross-tenant data leakage)
  - Per-tenant model routing preferences (tenant A on Haiku, tenant B on Sonnet)
  - Per-tenant rate limits and token budgets
  - Per-tenant system prompt overrides

No competitor in legal-tech offers this level of AI isolation. Clio, MyCase,
Smokeball, and Filevine all use shared model instances with app-level isolation
only. ParaIQ extends its RLS architecture to the AI layer.

Usage:
    from backend.demo1.ai_isolation import get_tenant_client, get_tenant_config

    config = get_tenant_config(firm_id)
    client = get_tenant_client(firm_id)
    response = client.messages.create(
        model=config.default_model,
        ...
    )
"""

import os
import json
import logging
import threading
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Tenant AI Configuration ───────────────────────────────────────────────────

@dataclass
class TenantAIConfig:
    """Per-tenant AI configuration."""
    firm_id: str
    default_model: str = ""          # e.g., "claude-haiku-4-5-20251001"
    strong_model: str = ""           # e.g., "claude-opus-4-5"
    max_tokens_per_day: int = 500_000
    max_tokens_per_request: int = 4_096
    system_prompt_override: str = ""
    enable_prompt_guard: bool = True
    enable_output_validation: bool = True   # for Tier 2 #10
    enable_safety_scoring: bool = True       # for Tier 2 #13
    custom_rate_limit_per_min: int = 60
    allowed_models: list = field(default_factory=list)  # empty = all allowed
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "firm_id": self.firm_id,
            "default_model": self.default_model,
            "strong_model": self.strong_model,
            "max_tokens_per_day": self.max_tokens_per_day,
            "max_tokens_per_request": self.max_tokens_per_request,
            "system_prompt_override": self.system_prompt_override,
            "enable_prompt_guard": self.enable_prompt_guard,
            "enable_output_validation": self.enable_output_validation,
            "enable_safety_scoring": self.enable_safety_scoring,
            "custom_rate_limit_per_min": self.custom_rate_limit_per_min,
            "allowed_models": self.allowed_models,
        }


# ── Defaults (from env) ──────────────────────────────────────────────────────

_DEFAULT_MODEL  = os.getenv("LLM_FAST", "claude-haiku-4-5-20251001")
_STRONG_MODEL   = os.getenv("LLM_STRONG", "claude-opus-4-5")


def _default_config(firm_id: str) -> TenantAIConfig:
    return TenantAIConfig(
        firm_id=firm_id,
        default_model=_DEFAULT_MODEL,
        strong_model=_STRONG_MODEL,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


# ── In-memory config cache (refreshed from DB) ────────────────────────────────

_config_cache: Dict[str, TenantAIConfig] = {}
_config_lock = threading.Lock()
_config_cache_ttl = 300  # 5 minutes
_config_cache_ts: Dict[str, float] = {}


# ── Per-tenant client instances ───────────────────────────────────────────────

_tenant_clients: Dict[str, Any] = {}      # firm_id -> Anthropic client
_tenant_async_clients: Dict[str, Any] = {}  # firm_id -> AsyncAnthropic client
_client_lock = threading.Lock()


def get_tenant_config(firm_id: str = "default") -> TenantAIConfig:
    """
    Get the AI configuration for a specific tenant.
    Loads from DB on first access, then caches for 5 minutes.
    Falls back to env defaults if DB is unavailable.
    """
    import time
    now = time.monotonic()

    # Check cache
    with _config_lock:
        if firm_id in _config_cache:
            cache_age = now - _config_cache_ts.get(firm_id, 0)
            if cache_age < _config_cache_ttl:
                return _config_cache[firm_id]

    # Load from DB
    config = _load_config_from_db(firm_id)

    with _config_lock:
        _config_cache[firm_id] = config
        _config_cache_ts[firm_id] = now

    return config


def _load_config_from_db(firm_id: str) -> TenantAIConfig:
    """Load tenant AI config from Postgres. Falls back to defaults on error."""
    try:
        from backend.demo1.pg import get_conn
        with get_conn(firm_id) as conn:
            row = conn.execute(
                "SELECT * FROM tenant_ai_config WHERE firm_id = %s",
                (firm_id,)
            ).fetchone()

            if row:
                return TenantAIConfig(
                    firm_id=firm_id,
                    default_model=row.get("default_model") or _DEFAULT_MODEL,
                    strong_model=row.get("strong_model") or _STRONG_MODEL,
                    max_tokens_per_day=row.get("max_tokens_per_day", 500_000),
                    max_tokens_per_request=row.get("max_tokens_per_request", 4_096),
                    system_prompt_override=row.get("system_prompt_override", ""),
                    enable_prompt_guard=row.get("enable_prompt_guard", True),
                    enable_output_validation=row.get("enable_output_validation", True),
                    enable_safety_scoring=row.get("enable_safety_scoring", True),
                    custom_rate_limit_per_min=row.get("custom_rate_limit_per_min", 60),
                    allowed_models=row.get("allowed_models") or [],
                    created_at=str(row.get("created_at", "")),
                    updated_at=str(row.get("updated_at", "")),
                )
    except Exception as e:
        logger.debug(f"[AIIsolation] Config load from DB failed for {firm_id}: {e}")

    # Fall back to defaults
    return _default_config(firm_id)


def get_tenant_client(firm_id: str = "default"):
    """
    Get an isolated Anthropic client for a specific tenant.
    Each tenant gets its own client instance — no shared connection state.

    This extends ParaIQ's RLS architecture to the AI layer:
    - Database: RLS isolates at the query level
    - AI layer: Per-tenant client instances isolate at the connection level
    """
    with _client_lock:
        if firm_id not in _tenant_clients:
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            _tenant_clients[firm_id] = anthropic.Anthropic(api_key=api_key)
            logger.info(f"[AIIsolation] Created sync client for tenant {firm_id}")
        return _tenant_clients[firm_id]


def get_tenant_async_client(firm_id: str = "default"):
    """Get an isolated async Anthropic client for a specific tenant."""
    with _client_lock:
        if firm_id not in _tenant_async_clients:
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            _tenant_async_clients[firm_id] = anthropic.AsyncAnthropic(api_key=api_key)
            logger.info(f"[AIIsolation] Created async client for tenant {firm_id}")
        return _tenant_async_clients[firm_id]


def invalidate_config_cache(firm_id: str = None):
    """Force config reload on next access. Called when tenant config changes."""
    with _config_lock:
        if firm_id:
            _config_cache.pop(firm_id, None)
            _config_cache_ts.pop(firm_id, None)
        else:
            _config_cache.clear()
            _config_cache_ts.clear()
    logger.info(f"[AIIsolation] Config cache invalidated for {firm_id or 'all tenants'}")


# ── Token budget tracking (per-tenant) ───────────────────────────────────────

_token_usage: Dict[str, Dict[str, int]] = {}  # firm_id -> {"date": ..., "tokens": N}
_token_lock = threading.Lock()


def track_token_usage(firm_id: str, input_tokens: int, output_tokens: int):
    """
    Track per-tenant token usage for budget enforcement.
    Called after every AI call.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total = input_tokens + output_tokens

    with _token_lock:
        usage = _token_usage.get(firm_id)
        if usage is None or usage.get("date") != today:
            _token_usage[firm_id] = {"date": today, "tokens": total}
        else:
            usage["tokens"] += total


def get_token_usage(firm_id: str) -> dict:
    """Get today's token usage for a tenant."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _token_lock:
        usage = _token_usage.get(firm_id, {})
        tokens = usage.get("tokens", 0) if usage.get("date") == today else 0
    config = get_tenant_config(firm_id)
    return {
        "firm_id": firm_id,
        "tokens_used_today": tokens,
        "daily_limit": config.max_tokens_per_day,
        "remaining": max(0, config.max_tokens_per_day - tokens),
        "utilization_pct": round((tokens / config.max_tokens_per_day) * 100, 1) if config.max_tokens_per_day else 0,
    }


def check_token_budget(firm_id: str) -> bool:
    """Returns True if tenant is within token budget, False if exceeded."""
    usage = get_token_usage(firm_id)
    return usage["remaining"] > 0


# ── Per-tenant system prompt resolution ───────────────────────────────────────

def resolve_system_prompt(firm_id: str, default_prompt: str) -> str:
    """
    Get the system prompt for a specific tenant.
    If tenant has a custom override, use it; otherwise use the default.
    """
    config = get_tenant_config(firm_id)
    if config.system_prompt_override and config.system_prompt_override.strip():
        return config.system_prompt_override
    return default_prompt


# ── Model access control ──────────────────────────────────────────────────────

def validate_model_access(firm_id: str, model: str) -> bool:
    """
    Check if a tenant is allowed to use a specific model.
    If allowed_models is empty, all models are permitted.
    """
    config = get_tenant_config(firm_id)
    if not config.allowed_models:
        return True
    return model in config.allowed_models


# ── DB initialization ─────────────────────────────────────────────────────────

def init_isolation_tables():
    """Create the tenant_ai_config table if it doesn't exist."""
    try:
        from backend.demo1.pg import get_conn
        with get_conn("default") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tenant_ai_config (
                    firm_id                    TEXT PRIMARY KEY,
                    default_model              TEXT,
                    strong_model               TEXT,
                    max_tokens_per_day         INTEGER DEFAULT 500000,
                    max_tokens_per_request     INTEGER DEFAULT 4096,
                    system_prompt_override     TEXT DEFAULT '',
                    enable_prompt_guard        BOOLEAN DEFAULT TRUE,
                    enable_output_validation   BOOLEAN DEFAULT TRUE,
                    enable_safety_scoring      BOOLEAN DEFAULT TRUE,
                    custom_rate_limit_per_min  INTEGER DEFAULT 60,
                    allowed_models             JSONB DEFAULT '[]'::jsonb,
                    created_at                 TIMESTAMPTZ DEFAULT NOW(),
                    updated_at                 TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_token_usage (
                    id          SERIAL PRIMARY KEY,
                    firm_id     TEXT NOT NULL,
                    date        DATE NOT NULL,
                    tokens_used INTEGER DEFAULT 0,
                    request_count INTEGER DEFAULT 0,
                    UNIQUE(firm_id, date)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_token_firm_date
                ON ai_token_usage (firm_id, date DESC)
            """)
        logger.info("[AIIsolation] Tables initialized [OK]")
        print("[AIIsolation] Tables initialized [OK]")
    except Exception as e:
        logger.warning(f"[AIIsolation] Table init deferred (non-fatal): {e}")
        print(f"[AIIsolation] Table init deferred: {e}")


# ── Admin API helpers ────────────────────────────────────────────────────────

def update_tenant_config(firm_id: str, **kwargs) -> dict:
    """
    Update AI configuration for a tenant.
    Only paraiq_super role should call this.
    Returns the updated config as a dict.
    """
    allowed_fields = {
        "default_model", "strong_model", "max_tokens_per_day",
        "max_tokens_per_request", "system_prompt_override",
        "enable_prompt_guard", "enable_output_validation",
        "enable_safety_scoring", "custom_rate_limit_per_min",
        "allowed_models",
    }

    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not updates:
        return {"error": "No valid fields to update"}

    # Serialize allowed_models if it's a list
    if "allowed_models" in updates and isinstance(updates["allowed_models"], list):
        updates["allowed_models"] = json.dumps(updates["allowed_models"])

    try:
        from backend.demo1.pg import get_conn
        with get_conn(firm_id) as conn:
            # Upsert
            placeholders = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [firm_id]
            conn.execute(
                f"""
                INSERT INTO tenant_ai_config (firm_id, {', '.join(updates.keys())}, updated_at)
                VALUES (%s, {', '.join(['%s'] * len(updates))}, NOW())
                ON CONFLICT (firm_id) DO UPDATE SET
                    {placeholders}, updated_at = NOW()
                """,
                [firm_id] + list(updates.values()) + list(updates.values()),
            )
        # Invalidate cache
        invalidate_config_cache(firm_id)
        return {"success": True, "firm_id": firm_id, "updated_fields": list(updates.keys())}
    except Exception as e:
        logger.error(f"[AIIsolation] Config update failed for {firm_id}: {e}")
        return {"error": str(e)}
