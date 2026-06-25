"""
backend/demo1/mlops/drift_monitor.py
=====================================
ParaIQ Model Drift Monitor.
Detects when Claude response quality or latency degrades over time.

Checks:
  1. Latency drift  — rolling avg latency > 2x baseline
  2. Cost drift     — rolling avg cost > 1.5x baseline  
  3. Error rate     — error % in last hour > 10%
  4. Token drift    — avg prompt tokens changed > 30% (prompt engineering regression)

Run as a cron job or call from APScheduler.
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import mlflow

MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5050")
logger     = logging.getLogger("paraiq.drift_monitor")

# Baseline thresholds (set from initial production observations)
BASELINES = {
    "latency_ms":    3000.0,   # alert if rolling avg > 2x this
    "cost_usd":      0.002,    # alert if rolling avg > 1.5x this
    "prompt_tokens": 500.0,    # alert if rolling avg changes > 30%
}

ALERT_MULTIPLIERS = {
    "latency_ms":    2.0,
    "cost_usd":      1.5,
    "prompt_tokens": 1.3,
}


def _get_recent_runs(hours: int = 1, experiment: str = "paraiq_claude_calls") -> list:
    """Fetch MLflow runs from the last N hours."""
    mlflow.set_tracking_uri(MLFLOW_URI)
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cutoff_ms = int(cutoff.timestamp() * 1000)
        runs = mlflow.search_runs(
            experiment_names=[experiment],
            filter_string=f"attributes.start_time > {cutoff_ms}",
            order_by=["start_time DESC"],
            max_results=200,
        )
        if runs.empty:
            return []
        return runs.to_dict("records")
    except Exception as e:
        logger.warning(f"[DriftMonitor] Could not fetch runs: {e}")
        return []


def check_drift() -> dict:
    """
    Run all drift checks. Returns a report dict with alerts.
    """
    runs = _get_recent_runs(hours=1)
    report = {
        "checked_at":  datetime.now(timezone.utc).isoformat(),
        "runs_checked": len(runs),
        "alerts":      [],
        "metrics":     {},
        "status":      "ok",
    }

    if not runs:
        report["status"] = "no_data"
        report["alerts"].append("No runs in last hour — model may not be receiving traffic")
        return report

    # Extract metrics
    latencies  = [r.get("metrics.latency_ms", 0)    for r in runs if r.get("metrics.latency_ms")]
    costs      = [r.get("metrics.cost_usd", 0)       for r in runs if r.get("metrics.cost_usd")]
    tokens     = [r.get("metrics.prompt_tokens", 0)  for r in runs if r.get("metrics.prompt_tokens")]
    errors     = [r for r in runs if r.get("tags.status") == "error"]

    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    avg_cost    = sum(costs)     / len(costs)     if costs     else 0
    avg_tokens  = sum(tokens)    / len(tokens)    if tokens    else 0
    error_rate  = len(errors)    / len(runs)      if runs      else 0

    report["metrics"] = {
        "avg_latency_ms":  round(avg_latency, 2),
        "avg_cost_usd":    round(avg_cost, 6),
        "avg_prompt_tokens": round(avg_tokens, 1),
        "error_rate_pct":  round(error_rate * 100, 1),
        "total_runs":      len(runs),
        "error_count":     len(errors),
    }

    # Check latency drift
    if avg_latency > BASELINES["latency_ms"] * ALERT_MULTIPLIERS["latency_ms"]:
        report["alerts"].append(
            f"LATENCY DRIFT: avg {avg_latency:.0f}ms > "
            f"{BASELINES['latency_ms'] * ALERT_MULTIPLIERS['latency_ms']:.0f}ms threshold"
        )

    # Check cost drift
    if avg_cost > BASELINES["cost_usd"] * ALERT_MULTIPLIERS["cost_usd"]:
        report["alerts"].append(
            f"COST DRIFT: avg ${avg_cost:.4f} > "
            f"${BASELINES['cost_usd'] * ALERT_MULTIPLIERS['cost_usd']:.4f} threshold"
        )

    # Check token drift (prompt engineering regression)
    if avg_tokens > BASELINES["prompt_tokens"] * ALERT_MULTIPLIERS["prompt_tokens"]:
        report["alerts"].append(
            f"TOKEN DRIFT: avg {avg_tokens:.0f} tokens > "
            f"{BASELINES['prompt_tokens'] * ALERT_MULTIPLIERS['prompt_tokens']:.0f} threshold — "
            f"possible prompt regression"
        )

    # Check error rate
    if error_rate > 0.10:
        report["alerts"].append(
            f"HIGH ERROR RATE: {error_rate*100:.1f}% of runs failed in last hour"
        )

    if report["alerts"]:
        report["status"] = "alert"
        for alert in report["alerts"]:
            logger.warning(f"[DriftMonitor] {alert}")
    else:
        logger.info(f"[DriftMonitor] OK — {len(runs)} runs, "
                    f"avg latency {avg_latency:.0f}ms, "
                    f"avg cost ${avg_cost:.4f}")

    return report


def log_drift_check(report: dict):
    """Log drift check results to MLflow for trend tracking."""
    mlflow.set_tracking_uri(MLFLOW_URI)
    try:
        mlflow.set_experiment("paraiq_drift_monitor")
        with mlflow.start_run(tags={
            "status":      report["status"],
            "alert_count": str(len(report.get("alerts", []))),
        }):
            metrics = report.get("metrics", {})
            if metrics:
                mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
    except Exception as e:
        logger.debug(f"[DriftMonitor] MLflow log failed (non-fatal): {e}")
