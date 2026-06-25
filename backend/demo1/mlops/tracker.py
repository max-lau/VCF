"""
backend/demo1/mlops/tracker.py
==============================
ParaIQ MLflow experiment tracker.
Logs every Claude inference call with inputs, outputs, latency, token usage, and cost.

Usage:
    from backend.demo1.mlops.tracker import log_inference
    log_inference(
        experiment="paraiq_analyze",
        firm_id="firm_abc",
        model="claude-haiku-4-5-20251001",
        prompt_tokens=450,
        completion_tokens=120,
        latency_ms=1240,
        endpoint="/analyze",
        status="success",
    )
"""
import os
import time
import mlflow
from pathlib import Path

# MLflow tracking URI — local SQLite by default, overridable via env
MLFLOW_URI = os.environ.get(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{Path(__file__).parent.parent.parent.parent / 'mlflow.db'}"
)

# Cost per million tokens (Anthropic pricing as of 2026)
_COST_PER_M = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00},
}
_DEFAULT_COST = {"input": 3.00, "output": 15.00}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = _COST_PER_M.get(model, _DEFAULT_COST)
    return round(
        (prompt_tokens    / 1_000_000) * pricing["input"] +
        (completion_tokens / 1_000_000) * pricing["output"],
        6
    )


def get_tracker():
    """Return a configured MLflow client pointed at the tracking server."""
    mlflow.set_tracking_uri(MLFLOW_URI)
    return mlflow


def log_inference(
    experiment:         str,
    endpoint:           str,
    model:              str,
    prompt_tokens:      int,
    completion_tokens:  int,
    latency_ms:         float,
    firm_id:            str  = "default",
    status:             str  = "success",
    error:              str  = None,
    extra_tags:         dict = None,
    extra_metrics:      dict = None,
) -> str:
    """
    Log a single Claude inference call as an MLflow run.
    Returns the run_id for reference.
    """
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(experiment)

    cost_usd = _estimate_cost(model, prompt_tokens, completion_tokens)
    total_tokens = prompt_tokens + completion_tokens

    tags = {
        "firm_id":  firm_id,
        "endpoint": endpoint,
        "model":    model,
        "status":   status,
        "env":      os.environ.get("TESTING", "0") == "1" and "ci" or "production",
    }
    if error:
        tags["error"] = str(error)[:250]
    if extra_tags:
        tags.update(extra_tags)

    metrics = {
        "prompt_tokens":     prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens":      total_tokens,
        "latency_ms":        round(latency_ms, 2),
        "cost_usd":          cost_usd,
        "tokens_per_second": round((total_tokens / latency_ms) * 1000, 2) if latency_ms > 0 else 0,
    }
    if extra_metrics:
        metrics.update(extra_metrics)

    with mlflow.start_run(tags=tags) as run:
        mlflow.log_metrics(metrics)
        return run.info.run_id


def log_batch_run(
    experiment:    str,
    firm_id:       str,
    docs_processed: int,
    llm_calls:     int,
    total_tokens:  int,
    elapsed_s:     float,
    cost_usd:      float,
    status:        str = "completed",
    abort_reason:  str = None,
) -> str:
    """Log a guarded discovery batch run."""
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(experiment)

    tags = {"firm_id": firm_id, "status": status}
    if abort_reason:
        tags["abort_reason"] = abort_reason[:250]

    metrics = {
        "docs_processed": docs_processed,
        "llm_calls":      llm_calls,
        "total_tokens":   total_tokens,
        "elapsed_s":      round(elapsed_s, 2),
        "cost_usd":       round(cost_usd, 6),
        "docs_per_dollar": round(docs_processed / cost_usd, 2) if cost_usd > 0 else 0,
    }

    with mlflow.start_run(tags=tags) as run:
        mlflow.log_metrics(metrics)
        return run.info.run_id
