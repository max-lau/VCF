"""
model_router.py
===============
ParaIQ Multi-Model Routing with Fallback (#14)

Intelligently routes AI requests to the optimal model based on task type,
with automatic fallback on model failure. Per-tenant model preference override.
Cost tracking per model.

No competitor offers this — Clio is locked to OpenAI, MyCase to proprietary,
Smokeball to its own stack. ParaIQ's multi-model routing enables:
  - Cost optimization (cheap model for simple tasks, powerful for complex)
  - Resilience (automatic fallback on model outage)
  - Flexibility (per-tenant model preference)
  - Future-proofing (add new models without code changes)

Usage:
    from backend.demo1.model_router import call_llm

    response = call_llm(
        task_type="summarization",
        messages=messages,
        system="You are a legal analyst...",
        firm_id="acme_law",
        max_tokens=1000,
    )

Task types → model mapping (configurable):
  - summarization    → fast model (Haiku)
  - drafting         → strong model (Sonnet/Opus)
  - research         → strong model (Opus)
  - extraction       → fast model (Haiku)
  - classification   → fast model (Haiku)
  - analysis         → strong model (Sonnet)
  - quick_qa         → fast model (Haiku)
  - time_capture     → fast model (Haiku)
  - default          → fast model (Haiku)
"""

import os
import time
import logging
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


# ── Task types ────────────────────────────────────────────────────────────────

class TaskType(str, Enum):
    SUMMARIZATION   = "summarization"
    DRAFTING        = "drafting"
    RESEARCH        = "research"
    EXTRACTION      = "extraction"
    CLASSIFICATION  = "classification"
    ANALYSIS        = "analysis"
    QUICK_QA        = "quick_qa"
    TIME_CAPTURE    = "time_capture"
    CLIENT_COMMS    = "client_comms"
    DOCUMENT_REVIEW = "document_review"
    LEGAL_RESEARCH  = "legal_research"
    DEFAULT         = "default"


# ── Model definitions ──────────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    """Configuration for a single LLM model."""
    name: str
    provider: str           # "anthropic", "openai", etc.
    max_tokens: int         # max output tokens
    cost_per_1k_input: float   # USD per 1K input tokens
    cost_per_1k_output: float  # USD per 1K output tokens
    avg_latency_ms: int     # typical response time
    strengths: List[str]   # what this model is good at


# Default models (loaded from env with sensible defaults)
_DEFAULT_FAST  = os.getenv("LLM_FAST", "claude-haiku-4-5-20251001")
_DEFAULT_MEDIUM = os.getenv("LLM_MEDIUM", "claude-sonnet-4-5-20250929")
_DEFAULT_STRONG = os.getenv("LLM_STRONG", "claude-opus-4-5")

_MODELS: Dict[str, ModelConfig] = {
    _DEFAULT_FAST: ModelConfig(
        name=_DEFAULT_FAST, provider="anthropic",
        max_tokens=8192, cost_per_1k_input=0.25, cost_per_1k_output=1.25,
        avg_latency_ms=1500, strengths=["summarization", "extraction", "classification", "quick_qa"],
    ),
    _DEFAULT_MEDIUM: ModelConfig(
        name=_DEFAULT_MEDIUM, provider="anthropic",
        max_tokens=8192, cost_per_1k_input=3.0, cost_per_1k_output=15.0,
        avg_latency_ms=3000, strengths=["analysis", "drafting", "document_review"],
    ),
    _DEFAULT_STRONG: ModelConfig(
        name=_DEFAULT_STRONG, provider="anthropic",
        max_tokens=8192, cost_per_1k_input=15.0, cost_per_1k_output=75.0,
        avg_latency_ms=5000, strengths=["research", "legal_research", "complex_reasoning"],
    ),
}

# ── Task → Model routing table ────────────────────────────────────────────────

_DEFAULT_ROUTING: Dict[str, str] = {
    TaskType.SUMMARIZATION.value:    _DEFAULT_FAST,
    TaskType.EXTRACTION.value:        _DEFAULT_FAST,
    TaskType.CLASSIFICATION.value:    _DEFAULT_FAST,
    TaskType.QUICK_QA.value:          _DEFAULT_FAST,
    TaskType.TIME_CAPTURE.value:      _DEFAULT_FAST,
    TaskType.DRAFTING.value:          _DEFAULT_MEDIUM,
    TaskType.ANALYSIS.value:          _DEFAULT_MEDIUM,
    TaskType.DOCUMENT_REVIEW.value:   _DEFAULT_MEDIUM,
    TaskType.CLIENT_COMMS.value:      _DEFAULT_FAST,
    TaskType.RESEARCH.value:          _DEFAULT_STRONG,
    TaskType.LEGAL_RESEARCH.value:    _DEFAULT_STRONG,
    TaskType.DEFAULT.value:           _DEFAULT_FAST,
}

# ── Fallback chains (model → list of fallback models) ─────────────────────────

_FALLBACK_CHAINS: Dict[str, List[str]] = {
    _DEFAULT_FAST:   [_DEFAULT_MEDIUM, _DEFAULT_STRONG],
    _DEFAULT_MEDIUM: [_DEFAULT_FAST, _DEFAULT_STRONG],
    _DEFAULT_STRONG: [_DEFAULT_MEDIUM, _DEFAULT_FAST],
}

# ── Circuit breaker state ─────────────────────────────────────────────────────

@dataclass
class CircuitState:
    """Circuit breaker state for a model."""
    failure_count: int = 0
    last_failure_ts: float = 0
    is_open: bool = False
    opened_until: float = 0  # timestamp when circuit resets


_CIRCUIT_BREAKER_THRESHOLD = 3       # consecutive failures before opening
_CIRCUIT_BREAKER_RESET_S = 60       # seconds before trying again
_circuit_state: Dict[str, CircuitState] = {}
_circuit_lock = threading.Lock()


def _get_circuit(model: str) -> CircuitState:
    with _circuit_lock:
        if model not in _circuit_state:
            _circuit_state[model] = CircuitState()
        return _circuit_state[model]


def _is_circuit_open(model: str) -> bool:
    circuit = _get_circuit(model)
    if not circuit.is_open:
        return False
    now = time.monotonic()
    if now >= circuit.opened_until:
        # Half-open: allow one test request
        circuit.is_open = False
        circuit.failure_count = 0
        logger.info(f"[ModelRouter] Circuit half-open for {model}")
        return False
    return True


def _record_success(model: str):
    circuit = _get_circuit(model)
    circuit.failure_count = 0
    circuit.is_open = False


def _record_failure(model: str):
    circuit = _get_circuit(model)
    circuit.failure_count += 1
    circuit.last_failure_ts = time.monotonic()
    if circuit.failure_count >= _CIRCUIT_BREAKER_THRESHOLD:
        circuit.is_open = True
        circuit.opened_until = time.monotonic() + _CIRCUIT_BREAKER_RESET_S
        logger.warning(
            f"[ModelRouter] Circuit opened for {model} "
            f"after {circuit.failure_count} failures. "
            f"Retry in {_CIRCUIT_BREAKER_RESET_S}s."
        )


# ── Cost tracking ─────────────────────────────────────────────────────────────

_cost_tracker: Dict[str, Dict[str, float]] = {}  # firm_id -> {model -> cost}
_cost_lock = threading.Lock()
_request_log: List[dict] = []
_request_log_lock = threading.Lock()
_MAX_REQUEST_LOG = 1000  # keep last 1000 requests in memory


def _track_cost(firm_id: str, model: str, input_tokens: int, output_tokens: int):
    """Track API cost per tenant per model."""
    model_cfg = _MODELS.get(model)
    if not model_cfg:
        return
    cost = (input_tokens / 1000 * model_cfg.cost_per_1k_input) + \
           (output_tokens / 1000 * model_cfg.cost_per_1k_output)

    with _cost_lock:
        if firm_id not in _cost_tracker:
            _cost_tracker[firm_id] = {}
        _cost_tracker[firm_id][model] = _cost_tracker[firm_id].get(model, 0) + cost

    # Also track token usage in ai_isolation
    try:
        from backend.demo1.ai_isolation import track_token_usage
        track_token_usage(firm_id, input_tokens, output_tokens)
    except ImportError:
        pass


def _log_request(firm_id: str, model: str, task_type: str, input_tokens: int,
                 output_tokens: int, latency_ms: float, success: bool,
                 fallback_used: bool, error: str = ""):
    """Keep an in-memory log of recent AI requests."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "firm_id": firm_id,
        "model": model,
        "task_type": task_type,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": round(latency_ms, 1),
        "success": success,
        "fallback_used": fallback_used,
        "error": error[:200] if error else "",
    }
    with _request_log_lock:
        _request_log.append(entry)
        if len(_request_log) > _MAX_REQUEST_LOG:
            _request_log.pop(0)


# ── Core routing function ─────────────────────────────────────────────────────

def get_model_for_task(task_type: str, firm_id: str = "default") -> str:
    """
    Determine the best model for a given task type and tenant.
    Checks tenant-specific overrides first, then falls back to default routing.
    """
    # Check tenant override
    try:
        from backend.demo1.ai_isolation import get_tenant_config
        config = get_tenant_config(firm_id)
        # If tenant has specific allowed_models and it's not empty, prefer those
        if config.allowed_models:
            # Find the best allowed model for this task
            default_model = _DEFAULT_ROUTING.get(task_type, _DEFAULT_ROUTING[TaskType.DEFAULT.value])
            if default_model in config.allowed_models:
                return default_model
            # Return first allowed model as fallback
            return config.allowed_models[0]
    except ImportError:
        pass

    return _DEFAULT_ROUTING.get(task_type, _DEFAULT_ROUTING[TaskType.DEFAULT.value])


def get_fallback_chain(model: str) -> List[str]:
    """Get the fallback chain for a model."""
    chain = _FALLBACK_CHAINS.get(model, [])
    # Filter out models with open circuits
    return [m for m in chain if not _is_circuit_open(m)]


def call_llm(
    *,
    messages: List[Dict],
    system: str,
    firm_id: str = "default",
    task_type: str = TaskType.DEFAULT.value,
    max_tokens: int = 1024,
    **kwargs,
) -> Tuple[Any, dict]:
    """
    Call the LLM with intelligent routing and automatic fallback.

    Args:
        messages: LLM messages list.
        system: System prompt.
        firm_id: Tenant ID for isolation and routing.
        task_type: Type of task (determines model selection).
        max_tokens: Max output tokens.
        **kwargs: Additional kwargs passed to messages.create().

    Returns:
        (response, metadata) where metadata contains:
          - model_used, task_type, latency_ms, fallback_used,
          - input_tokens, output_tokens, cost_usd, circuit_state
    """
    from backend.demo1.rate_limit import check_rate_limit
    from backend.demo1.ai_isolation import (
        get_tenant_client, get_tenant_config, check_token_budget,
        validate_model_access, track_token_usage,
    )

    # ── Pre-flight checks ──
    check_rate_limit(firm_id, "ai")

    config = get_tenant_config(firm_id)
    if not check_token_budget(firm_id):
        raise _BudgetExceededError(
            f"Tenant {firm_id} has exceeded daily token budget "
            f"({config.max_tokens_per_day:,} tokens)"
        )

    # Determine model chain
    primary_model = get_model_for_task(task_type, firm_id)
    fallback_models = get_fallback_chain(primary_model)
    model_chain = [primary_model] + fallback_models

    # Filter by tenant's allowed models
    if config.allowed_models:
        model_chain = [m for m in model_chain if m in config.allowed_models]
        if not model_chain:
            raise _ModelAccessError(
                f"No allowed models available for tenant {firm_id} "
                f"(allowed: {config.allowed_models})"
            )

    # Enforce per-tenant max_tokens
    max_tokens = min(max_tokens, config.max_tokens_per_request)

    # Get isolated client for this tenant
    client = get_tenant_client(firm_id)

    # ── Try models in order ──
    last_error = None
    for i, model in enumerate(model_chain):
        is_fallback = i > 0

        if _is_circuit_open(model):
            logger.info(f"[ModelRouter] Skipping {model} (circuit open)")
            continue

        t0 = time.perf_counter()
        try:
            response = client.messages.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                system=system,
                **kwargs,
            )
            latency_ms = (time.perf_counter() - t0) * 1000

            # Track success
            _record_success(model)
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            _track_cost(firm_id, model, input_tokens, output_tokens)
            _log_request(
                firm_id, model, task_type, input_tokens, output_tokens,
                latency_ms, success=True, fallback_used=is_fallback,
            )

            metadata = {
                "model_used": model,
                "task_type": task_type,
                "latency_ms": round(latency_ms, 1),
                "fallback_used": is_fallback,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": _calculate_cost(model, input_tokens, output_tokens),
                "models_tried": model_chain[:i+1],
            }
            return response, metadata

        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            last_error = e
            _record_failure(model)
            _log_request(
                firm_id, model, task_type, 0, 0, latency_ms,
                success=False, fallback_used=is_fallback, error=str(e),
            )
            logger.warning(
                f"[ModelRouter] {model} failed for task={task_type}, "
                f"firm={firm_id}: {e}. "
                f"{'Trying fallback...' if i < len(model_chain) - 1 else 'No more fallbacks.'}"
            )
            continue

    # All models failed
    raise _AllModelsFailedError(
        f"All models failed for task={task_type}, firm={firm_id}. "
        f"Models tried: {model_chain}. Last error: {last_error}"
    )


# ── Async version ─────────────────────────────────────────────────────────────

async def call_llm_async(
    *,
    messages: List[Dict],
    system: str,
    firm_id: str = "default",
    task_type: str = TaskType.DEFAULT.value,
    max_tokens: int = 1024,
    **kwargs,
) -> Tuple[Any, dict]:
    """Async version of call_llm for use in async endpoints."""
    from backend.demo1.rate_limit import check_rate_limit
    from backend.demo1.ai_isolation import (
        get_tenant_async_client, get_tenant_config, check_token_budget,
        validate_model_access, track_token_usage,
    )

    check_rate_limit(firm_id, "ai")

    config = get_tenant_config(firm_id)
    if not check_token_budget(firm_id):
        raise _BudgetExceededError(
            f"Tenant {firm_id} has exceeded daily token budget"
        )

    primary_model = get_model_for_task(task_type, firm_id)
    fallback_models = get_fallback_chain(primary_model)
    model_chain = [primary_model] + fallback_models

    if config.allowed_models:
        model_chain = [m for m in model_chain if m in config.allowed_models]
        if not model_chain:
            raise _ModelAccessError(f"No allowed models for tenant {firm_id}")

    max_tokens = min(max_tokens, config.max_tokens_per_request)
    client = get_tenant_async_client(firm_id)

    last_error = None
    for i, model in enumerate(model_chain):
        is_fallback = i > 0
        if _is_circuit_open(model):
            continue

        t0 = time.perf_counter()
        try:
            response = await client.messages.create(
                model=model, messages=messages, max_tokens=max_tokens,
                system=system, **kwargs,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            _record_success(model)
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            _track_cost(firm_id, model, input_tokens, output_tokens)
            _log_request(
                firm_id, model, task_type, input_tokens, output_tokens,
                latency_ms, success=True, fallback_used=is_fallback,
            )
            metadata = {
                "model_used": model, "task_type": task_type,
                "latency_ms": round(latency_ms, 1), "fallback_used": is_fallback,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "cost_usd": _calculate_cost(model, input_tokens, output_tokens),
                "models_tried": model_chain[:i+1],
            }
            return response, metadata
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            last_error = e
            _record_failure(model)
            _log_request(
                firm_id, model, task_type, 0, 0, latency_ms,
                success=False, fallback_used=is_fallback, error=str(e),
            )
            continue

    raise _AllModelsFailedError(
        f"All models failed for task={task_type}, firm={firm_id}. Last error: {last_error}"
    )


# ── Cost calculation ──────────────────────────────────────────────────────────

def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the cost of an API call."""
    cfg = _MODELS.get(model)
    if not cfg:
        return 0.0
    return round(
        (input_tokens / 1000 * cfg.cost_per_1k_input) +
        (output_tokens / 1000 * cfg.cost_per_1k_output),
        6,
    )


# ── Status / monitoring ───────────────────────────────────────────────────────

def get_routing_status() -> dict:
    """Get current routing configuration and circuit breaker states."""
    with _circuit_lock:
        circuits = {
            model: {
                "is_open": state.is_open,
                "failure_count": state.failure_count,
                "resets_in_s": max(0, int(state.opened_until - time.monotonic())) if state.is_open else 0,
            }
            for model, state in _circuit_state.items()
        }

    return {
        "routing_table": _DEFAULT_ROUTING.copy(),
        "fallback_chains": _FALLBACK_CHAINS.copy(),
        "available_models": list(_MODELS.keys()),
        "circuit_breakers": circuits,
    }


def get_cost_report(firm_id: str = None) -> dict:
    """Get cost report for a tenant (or all tenants if None)."""
    with _cost_lock:
        if firm_id:
            costs = {firm_id: _cost_tracker.get(firm_id, {})}
        else:
            costs = dict(_cost_tracker)

    report = {}
    for fid, models in costs.items():
        report[fid] = {
            "by_model": {m: round(c, 4) for m, c in models.items()},
            "total": round(sum(models.values()), 4),
        }
    return report


def get_recent_requests(limit: int = 50, firm_id: str = None) -> list:
    """Get recent AI request logs."""
    with _request_log_lock:
        logs = list(_request_log[-limit:])
    if firm_id:
        logs = [l for l in logs if l["firm_id"] == firm_id]
    return list(reversed(logs))


# ── Custom exceptions ─────────────────────────────────────────────────────────

class _BudgetExceededError(Exception):
    """Tenant has exceeded their daily token budget."""


class _ModelAccessError(Exception):
    """No allowed models available for tenant."""


class _AllModelsFailedError(Exception):
    """All models in the fallback chain failed."""


# ── Initialization ────────────────────────────────────────────────────────────

def init_model_router():
    """Called at startup."""
    logger.info(
        f"[ModelRouter] Initialized — "
        f"{len(_MODELS)} models, {len(_DEFAULT_ROUTING)} task routes, "
        f"circuit breaker threshold={_CIRCUIT_BREAKER_THRESHOLD}"
    )
    print(
        f"[ModelRouter] Initialized — "
        f"{len(_MODELS)} models, {len(_DEFAULT_ROUTING)} task routes ✓"
    )
