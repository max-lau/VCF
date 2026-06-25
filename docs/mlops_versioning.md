# ParaIQ Model Versioning Strategy

**Date:** June 2026  
**Author:** Maxwell Lau  
**Scope:** Legal classifier models and LLM prompt versions in ParaIQ

---

## 1. Model Registry (MLflow)

All trained models are registered in the MLflow Model Registry at `http://localhost:5050`.

### Current Models

| Model Name | Version | Status | Accuracy | F1 | Train Size | Registered |
|---|---|---|---|---|---|---|
| paraiq-legal-classifier | v1 | READY | 33.3% | 0.254 | 48 samples | 2026-06-25 |

### Version Lifecycle
- **READY** — current production version, used by `/legal-bert/classify`
- **ARCHIVED** — superseded by newer version, kept for rollback

### Registering a New Version

```python
from backend.demo1.mlops.registry import register_model

version = register_model(
    model_path="models/legal_classifier",
    model_name="paraiq-legal-classifier",
    metrics={"accuracy": 0.87, "f1_score": 0.85},
    description="v2 — retrained on 480 samples with data augmentation",
)
```

---

## 2. Promotion Criteria

A new model version is promoted to production when:

| Metric | Minimum Threshold | Notes |
|---|---|---|
| Accuracy | > 0.75 | vs. v1 baseline of 0.33 |
| F1 Score | > 0.70 | macro-averaged across 3 labels |
| Train Size | ≥ 200 samples | diminishing returns below this |
| Eval Set | ≥ 50 held-out | must not overlap train set |

---

## 3. Drift Monitoring

The drift monitor (`backend/demo1/mlops/drift_monitor.py`) runs hourly via APScheduler and checks:

| Check | Threshold | Action |
|---|---|---|
| Latency drift | avg > 6000ms (2x baseline) | Log warning to MLflow + logger |
| Cost drift | avg > $0.003 (1.5x baseline) | Log warning |
| Token drift | avg > 650 tokens (1.3x baseline) | Suggests prompt regression |
| Error rate | > 10% in last hour | Log warning |

Results logged to `paraiq_drift_monitor` MLflow experiment for trend tracking.

---

## 4. LLM Prompt Versioning

Claude prompts are versioned implicitly via git commits. Convention:
Tracked via:
- A/B testing framework (`backend/demo1/ab_test.py`) for controlled experiments
- MLflow `paraiq_claude_calls` experiment for per-call metrics
- Langfuse traces for full prompt/response audit trail

---

## 5. Retraining Triggers

Retrain the legal classifier when:

1. **Accuracy drops** — drift monitor detects degraded metrics vs. registered baseline
2. **New label needed** — e.g. adding `SETTLEMENT_FAVORABLE` label
3. **Data threshold** — accumulated ≥ 100 new labeled samples since last training
4. **Scheduled** — quarterly retraining regardless of performance

### Retraining Command

```bash
cd /root/nlp-portfolio
# Via API (POST request)
curl -X POST http://localhost:5003/model/fine-tune \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"epochs": 5, "learning_rate": 2e-5}'

# Or directly
.venv/bin/python3 -c "
from backend.demo1.fine_tune import train_model
train_model(epochs=5, learning_rate=2e-5)
"
```

---

## 6. MLflow Experiments Reference

| Experiment | Purpose | Retention |
|---|---|---|
| `paraiq_claude_calls` | Per-call inference tracking | 90 days |
| `paraiq_discovery` | Batch discovery run tracking | 180 days |
| `paraiq_model_registry` | Model registration events | Forever |
| `paraiq_drift_monitor` | Hourly drift check results | 30 days |

---

## 7. Interview Talking Points

> "ParaIQ uses MLflow for end-to-end ML lifecycle management. Every Claude inference call is logged as an MLflow run with token counts, latency, and cost estimates. Trained models are registered in the MLflow Model Registry with promotion criteria — a model needs >75% accuracy and >200 training samples before it replaces the production version. An hourly drift monitor checks for latency, cost, and error rate anomalies and logs results back to MLflow for trend tracking. This gives us a full audit trail from training through production."
