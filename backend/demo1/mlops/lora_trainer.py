"""
backend/demo1/mlops/lora_trainer.py
=====================================
MLOps Module 3 — LoRA / PEFT Fine-tuning

Wraps the raw PyTorch training loop (Module 2) with PEFT LoRA adapters.
Instead of updating all 66M DistilBERT parameters, LoRA injects trainable
low-rank matrices into the attention layers — training only ~0.5% of parameters
while matching or exceeding full fine-tune accuracy on small datasets.

Why LoRA matters for ParaIQ:
  - Faster iterations: adapter training is 4-8x faster on CPU than full fine-tune
  - Multiple firm variants: each firm can have a specialised adapter (< 5MB)
    loaded on top of the shared frozen base model, rather than a 250MB full copy
  - Production pattern: base model loaded once, adapters swapped per-request

LoRA config:
  r=8       — rank of injected matrices (higher = more capacity, more params)
  alpha=32  — scaling factor (lora_alpha / r = effective learning rate scale)
  dropout=0.1
  target_modules: ["q_lin", "v_lin"]  — DistilBERT attention projections

MLflow experiment: "paraiq_lora_training"
Model saved to:   models/legal_classifier_lora/

Usage:
    python -m backend.demo1.mlops.lora_trainer

Or via API:
    POST /model/lora-train
"""

import os
import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Heavy imports (torch, mlflow, peft) are deferred to train()/load_lora_model()
# to keep CI startup fast. At import time only stdlib is needed.

# ── Paths ──────────────────────────────────────────────────────────────────────
MODEL_DIR  = Path("models/legal_classifier_lora")
MLFLOW_URI = os.environ.get(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{Path(__file__).parent.parent.parent.parent / 'mlflow.db'}"
)

# ── Label map ──────────────────────────────────────────────────────────────────
LABEL_MAP   = {"PROSECUTION_FAVORABLE": 0, "DEFENSE_FAVORABLE": 1, "NEUTRAL": 2}
ID_TO_LABEL = {v: k for k, v in LABEL_MAP.items()}

# ── Re-use dataset class and helpers from pytorch_trainer ─────────────────────
from backend.demo1.mlops.pytorch_trainer import (
    LegalDataset,
    accuracy,
    per_class_f1,
)
from backend.demo1.fine_tune import TRAINING_DATA


def _count_trainable_params(model) -> tuple[int, int]:
    """Return (trainable_params, total_params)."""
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total     = sum(p.numel() for p in model.parameters())
    return trainable, total


# ── LoRA training loop ─────────────────────────────────────────────────────────

def train(
    epochs:     int   = 5,
    batch_size: int   = 8,
    lr:         float = 3e-4,   # higher LR works well for LoRA adapters
    lora_r:     int   = 8,
    lora_alpha: int   = 32,
    lora_dropout: float = 0.1,
    seed:       int   = 42,
    firm_id:    str   = "default",
) -> dict:
    """
    LoRA fine-tuning loop for the legal sentence classifier.

    Key difference from pytorch_trainer.train():
      - Base DistilBERT weights are FROZEN (requires_grad=False)
      - PEFT injects trainable LoRA matrices into ["q_lin", "v_lin"]
      - Only ~0.5% of total parameters are updated
      - Adapters saved separately — base model reused across firms

    Per-epoch metrics logged to MLflow experiment "paraiq_lora_training".
    """
    MODEL_DIR = Path(f"models/{firm_id}/legal_classifier_lora")  # per-firm (shadows module constant)
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
    from torch.optim import AdamW
    from torch.optim.lr_scheduler import LinearLR
    import mlflow
    from peft import LoraConfig, TaskType, get_peft_model

    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"[LoRATrainer] device={device}, epochs={epochs}, r={lora_r}, alpha={lora_alpha}")

    # ── Load base model + tokenizer ────────────────────────────────────────────
    from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

    log.info("[LoRATrainer] Loading DistilBERT base model...")
    tokenizer = DistilBertTokenizerFast.from_pretrained("distilbert-base-uncased")
    base_model = DistilBertForSequenceClassification.from_pretrained(
        "distilbert-base-uncased",
        num_labels=3,
        id2label=ID_TO_LABEL,
        label2id=LABEL_MAP,
    )

    # ── Apply LoRA config ──────────────────────────────────────────────────────
    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=["q_lin", "v_lin"],   # DistilBERT attention projections
        bias="none",
        inference_mode=False,
    )
    model = get_peft_model(base_model, lora_config)
    model = model.to(device)

    trainable, total = _count_trainable_params(model)
    pct = round(100 * trainable / total, 3)
    log.info(
        f"[LoRATrainer] Trainable params: {trainable:,} / {total:,} ({pct}%) — "
        f"base model frozen, only LoRA adapters update"
    )

    # ── Data ───────────────────────────────────────────────────────────────────
    from sklearn.model_selection import train_test_split
    texts  = [t for t, _ in TRAINING_DATA]
    labels = [LABEL_MAP[l] for _, l in TRAINING_DATA]
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=seed, stratify=labels
    )

    train_dl = DataLoader(LegalDataset(train_texts, train_labels, tokenizer), batch_size=batch_size, shuffle=True)
    val_dl   = DataLoader(LegalDataset(val_texts,   val_labels,   tokenizer), batch_size=batch_size, shuffle=False)

    # ── Optimiser — only LoRA params ──────────────────────────────────────────
    optimiser = AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=lr, weight_decay=0.01
    )
    total_steps = len(train_dl) * epochs
    scheduler = LinearLR(optimiser, start_factor=1.0, end_factor=0.1, total_iters=total_steps)

    # ── MLflow run ─────────────────────────────────────────────────────────────
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment("paraiq_lora_training")

    best_acc   = 0.0
    best_epoch = 0
    final_f1s  = {}

    with mlflow.start_run(run_name=f"lora_r{lora_r}_e{epochs}") as run:
        mlflow.log_params({
            "model":            "distilbert-base-uncased+lora",
            "lora_r":           lora_r,
            "lora_alpha":       lora_alpha,
            "lora_dropout":     lora_dropout,
            "target_modules":   "q_lin,v_lin",
            "trainable_params": trainable,
            "total_params":     total,
            "trainable_pct":    pct,
            "epochs":           epochs,
            "batch_size":       batch_size,
            "lr":               lr,
            "train_size":       len(train_texts),
            "val_size":         len(val_texts),
            "device":           str(device),
        })

        t_start = time.time()

        for epoch in range(1, epochs + 1):
            # ── Train ──────────────────────────────────────────────────────────
            model.train()
            epoch_loss, epoch_steps = 0.0, 0

            for batch in train_dl:
                input_ids      = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                labels_batch   = batch["labels"].to(device)

                optimiser.zero_grad()
                outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels_batch)
                outputs.loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimiser.step()
                scheduler.step()

                epoch_loss  += outputs.loss.item()
                epoch_steps += 1

            train_loss = epoch_loss / epoch_steps

            # ── Validate ───────────────────────────────────────────────────────
            model.eval()
            all_logits, all_labels_list = [], []
            val_loss_total, val_steps   = 0.0, 0

            with torch.no_grad():
                for batch in val_dl:
                    input_ids      = batch["input_ids"].to(device)
                    attention_mask = batch["attention_mask"].to(device)
                    labels_batch   = batch["labels"].to(device)

                    outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels_batch)
                    val_loss_total += outputs.loss.item()
                    val_steps += 1
                    all_logits.append(outputs.logits.cpu())
                    all_labels_list.append(labels_batch.cpu())

            val_loss   = val_loss_total / val_steps
            logits_cat = torch.cat(all_logits)
            labels_cat = torch.cat(all_labels_list)
            val_acc    = accuracy(logits_cat, labels_cat)
            final_f1s  = per_class_f1(logits_cat, labels_cat)

            mlflow.log_metrics({
                "train_loss":   round(train_loss, 4),
                "val_loss":     round(val_loss, 4),
                "val_accuracy": round(val_acc, 4),
                "val_f1_macro": final_f1s["macro_avg"],
                "learning_rate": round(scheduler.get_last_lr()[0], 8),
                **{f"f1_{k.lower()[:4]}": v for k, v in final_f1s.items() if k != "macro_avg"},
            }, step=epoch)

            log.info(
                f"[LoRATrainer] Epoch {epoch}/{epochs} — "
                f"train_loss={train_loss:.4f}  val_loss={val_loss:.4f}  "
                f"val_acc={val_acc:.3f}  f1_macro={final_f1s['macro_avg']:.3f}"
            )

            # ── Save best adapter ──────────────────────────────────────────────
            if val_acc > best_acc:
                best_acc   = val_acc
                best_epoch = epoch
                MODEL_DIR.mkdir(parents=True, exist_ok=True)
                # save_pretrained on a PeftModel saves only the adapter weights
                model.save_pretrained(str(MODEL_DIR))
                tokenizer.save_pretrained(str(MODEL_DIR))
                log.info(f"[LoRATrainer] ✓ New best adapter saved (acc={best_acc:.3f})")

        elapsed = round(time.time() - t_start, 1)

        mlflow.log_metrics({
            "best_val_accuracy": round(best_acc, 4),
            "best_epoch":        best_epoch,
            "elapsed_s":         elapsed,
        })

    # ── Save metadata ──────────────────────────────────────────────────────────
    meta = {
        "model":            "distilbert-base-uncased+lora",
        "trainer":          "peft_lora",
        "task":             "legal-sentiment-classification",
        "lora_r":           lora_r,
        "lora_alpha":       lora_alpha,
        "lora_dropout":     lora_dropout,
        "target_modules":   ["q_lin", "v_lin"],
        "trainable_params": trainable,
        "total_params":     total,
        "trainable_pct":    pct,
        "labels":           list(LABEL_MAP.keys()),
        "train_size":       len(train_texts),
        "val_size":         len(val_texts),
        "epochs":           epochs,
        "best_epoch":       best_epoch,
        "accuracy":         round(best_acc, 4),
        "f1_macro":         final_f1s.get("macro_avg", 0),
        "elapsed_s":        elapsed,
        "trained_at":       datetime.now(timezone.utc).isoformat(),
        "mlflow_run_id":    run.info.run_id,
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_DIR / "training_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    log.info(
        f"[LoRATrainer] Complete — best_acc={best_acc:.3f} @ epoch {best_epoch}, "
        f"trainable_params={trainable:,} ({pct}%), elapsed={elapsed}s"
    )
    return {
        "val_accuracy":     round(best_acc, 4),
        "val_f1_macro":     final_f1s.get("macro_avg", 0),
        "best_epoch":       best_epoch,
        "total_epochs":     epochs,
        "trainable_params": trainable,
        "total_params":     total,
        "trainable_pct":    pct,
        "elapsed_s":        elapsed,
        "run_id":           run.info.run_id,
    }


# ── Inference with saved LoRA adapter ─────────────────────────────────────────

def load_lora_model():
    """
    Load base DistilBERT + LoRA adapter for inference.

    The base model is loaded once and shared. Adapters are lightweight
    (< 5MB) and can be swapped per firm without reloading the base.
    """
    from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification
    from peft import PeftModel

    if not (MODEL_DIR / "adapter_config.json").exists():
        raise FileNotFoundError(
            f"No LoRA adapter found at {MODEL_DIR}. Run train() first."
        )

    tokenizer  = DistilBertTokenizerFast.from_pretrained(str(MODEL_DIR))
    base_model = DistilBertForSequenceClassification.from_pretrained(
        "distilbert-base-uncased", num_labels=3
    )
    model = PeftModel.from_pretrained(base_model, str(MODEL_DIR))
    model.eval()
    return model, tokenizer


def predict_lora(text: str) -> dict:
    """Classify legal text using the saved LoRA adapter."""
    import torch
    model, tokenizer = load_lora_model()
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=128)
    with torch.no_grad():
        outputs = model(**inputs)
        probs   = torch.softmax(outputs.logits, dim=-1)[0]
        pred_id = probs.argmax().item()

    return {
        "label":      ID_TO_LABEL[pred_id],
        "confidence": round(probs[pred_id].item(), 4),
        "all_scores": {ID_TO_LABEL[i]: round(probs[i].item(), 4) for i in range(len(probs))},
        "model":      "distilbert+lora",
    }


# ── Standalone entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    results = train(epochs=5, lora_r=8, lora_alpha=32)
    print("\n=== LoRA Training Complete ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
