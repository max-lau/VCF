# ParaIQ MLOps — Module 2 & 3: PyTorch + LoRA Training

**Date:** June 2026  
**Author:** Maxwell Lau  
**Scope:** Raw PyTorch training loop (Module 2) and LoRA/PEFT fine-tuning (Module 3)

---

## Overview

ParaIQ's legal sentence classifier (PROSECUTION_FAVORABLE / DEFENSE_FAVORABLE / NEUTRAL)
was originally trained using HuggingFace `Trainer`. Modules 2 and 3 replace and extend
this with a hand-written PyTorch loop and then LoRA adapters, giving full control over
training dynamics and enabling per-firm model specialisation at < 5MB per client.

---

## Module 2 — Raw PyTorch Training Loop

**File:** `backend/demo1/mlops/pytorch_trainer.py`  
**Endpoint:** `POST /model/pytorch-train`  
**MLflow experiment:** `paraiq_pytorch_training`  
**Output:** `models/legal_classifier_pytorch/`

### What it builds

A full training loop without HuggingFace Trainer, including:

| Component | Choice | Reason |
|---|---|---|
| Optimiser | AdamW (lr=2e-5, wd=0.01) | Standard BERT fine-tuning recipe |
| Scheduler | LinearLR (warmup → 10% of lr) | Prevents late-training divergence |
| Gradient clipping | max_norm=1.0 | Stabilises DistilBERT on small datasets |
| Loss | CrossEntropyLoss (built into DistilBertForSequenceClassification) | 3-class CE |
| Metrics | accuracy + per-class F1 (hand-written, no sklearn at inference) | Dependency-free inference |

### Per-epoch MLflow metrics logged

```
train_loss, val_loss, val_accuracy, val_f1_macro,
f1_pros (PROSECUTION), f1_defe (DEFENSE), f1_neut (NEUTRAL),
learning_rate
```

### Key design decisions

- **Best-checkpoint saving** — only saves when `val_accuracy` improves, not at every epoch
- **Hand-written F1** — avoids importing sklearn at inference time; uses TP/FP/FN tensors
- **`filter(requires_grad=True)`** — pattern reused in Module 3 to train only LoRA params
- **`torch.manual_seed`** — deterministic splits for reproducibility across runs

---

## Module 3 — LoRA / PEFT Fine-tuning

**File:** `backend/demo1/mlops/lora_trainer.py`  
**Endpoint:** `POST /model/lora-train`  
**MLflow experiment:** `paraiq_lora_training`  
**Output:** `models/legal_classifier_lora/` (adapter weights only, ~5MB)

### What LoRA does

LoRA (Low-Rank Adaptation) injects trainable matrices `A` and `B` into frozen attention
layers. Instead of updating weight `W`, the effective weight becomes `W + (B × A) × scale`.
Only `A` and `B` are trained — the base model is frozen.

```
Standard fine-tune:  66,955,779 params trained  (100%)
LoRA (r=8):              ~300,000 params trained  (~0.5%)
```

### LoRA config

| Hyperparameter | Value | Notes |
|---|---|---|
| `r` (rank) | 8 | Low rank = fewer params; r=4..16 is the typical range |
| `lora_alpha` | 32 | Effective LR scale = alpha/r = 4; higher values weight adapters more |
| `lora_dropout` | 0.1 | Regularisation on adapter paths |
| `target_modules` | `["q_lin", "v_lin"]` | DistilBERT's query and value projections in attention |
| `bias` | `"none"` | Don't train bias terms (minimal accuracy impact) |
| `task_type` | `SEQ_CLS` | PEFT's sequence classification mode |

### Why `q_lin` and `v_lin`?

DistilBERT's attention modules name their projections `q_lin`, `k_lin`, `v_lin` (not `query`/`value` as in BERT).
Targeting query + value (not key) follows the original LoRA paper's recommendation — keys have less impact
on downstream task performance.

### Per-firm adapter pattern

```python
# Base model loaded ONCE (250MB), shared across firms
base = DistilBertForSequenceClassification.from_pretrained("distilbert-base-uncased")

# Per-firm adapter loaded on demand (< 5MB each)
firm_abc_model     = PeftModel.from_pretrained(base, "models/adapters/firm_abc/")
meridian_model     = PeftModel.from_pretrained(base, "models/adapters/meridian_legal/")
```

This is the production path for specialising ParaIQ's classifier per client without
multiplying storage costs.

---

## Comparison: Three Training Approaches

| Approach | Module | Params Trained | Speed (CPU) | Val Accuracy | Adapter Size |
|---|---|---|---|---|---|
| HuggingFace Trainer | Module 1 (fine_tune.py) | 66.9M (100%) | baseline | ~33% (48 samples) | 250MB |
| Raw PyTorch loop | Module 2 | 66.9M (100%) | similar | comparable | 250MB |
| LoRA (r=8) | Module 3 | ~300K (0.5%) | 4-8x faster | comparable | ~5MB |

*Accuracy is low (33%) because the dataset has only 60 samples. Target is > 75% at n≥200.*

---

## MLflow Experiments

| Experiment | Tracks | Run naming |
|---|---|---|
| `paraiq_pytorch_training` | Per-epoch train/val loss, accuracy, F1, LR | `distilbert_e{N}_lr{lr}` |
| `paraiq_lora_training` | Same + trainable_params, trainable_pct | `lora_r{r}_e{N}` |

View at: `http://localhost:5050` (MLflow server, PM2 id:5)

---

## Interview Talking Points

**"Walk me through your training infrastructure."**
> "I built two training loops in ParaIQ. The first is a raw PyTorch loop — hand-written gradient accumulation, AdamW with linear warmup decay, and gradient clipping at norm=1. Every epoch logs train loss, val loss, accuracy, and per-class F1 to MLflow. The second wraps that with PEFT LoRA, freezing the base DistilBERT and training only ~300K parameters out of 67M — about 0.5%. This is important for the multi-tenant case: each law firm can have a specialised adapter under 5MB sitting on top of a shared frozen base model."

**"Why LoRA specifically?"**
> "Three reasons: speed — adapter training is 4-8x faster on CPU; storage — 5MB adapters vs 250MB full copies per firm; and composability — you can swap adapters per-request without reloading the base model, which matters when you have dozens of tenants with different case specialisations."

**"How do you track experiments?"**
> "MLflow with a local SQLite backend. Every training run logs hyperparameters as params and per-epoch metrics as time-series. I can compare runs visually, and the model registry tracks which version is READY vs ARCHIVED with promotion criteria documented — accuracy > 75%, F1 > 0.70, train set ≥ 200 samples."

**"What's your model's current accuracy and what's the plan to improve it?"**
> "33% on 60 samples — which is roughly at-chance for 3 classes, so the baseline is honest. The plan is: expand training data to 200+ samples via semi-supervised labelling of real case documents (with Anthropic BAA in place), retrain, and target > 75%. LoRA makes iteration fast enough to do this without a GPU."

---

## Promotion Criteria (from mlops_versioning.md)

| Metric | Threshold | Current |
|---|---|---|
| Accuracy | > 75% | ~33% (n=60) |
| F1 macro | > 0.70 | ~0.25 |
| Train size | ≥ 200 samples | 60 |
| Eval set | ≥ 50 held-out | 12 |

Next training run should target n≥200 samples from real case data post-BAA.
