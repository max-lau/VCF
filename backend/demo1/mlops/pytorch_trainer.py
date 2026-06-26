"""
backend/demo1/mlops/pytorch_trainer.py
=======================================
MLOps Module 2 — Raw PyTorch Training Loop

Trains the legal sentence classifier (PROSECUTION_FAVORABLE / DEFENSE_FAVORABLE / NEUTRAL)
using a hand-written PyTorch training loop instead of HuggingFace Trainer.

Why a raw loop instead of Trainer?
  - Full control over gradient accumulation, learning-rate schedule, and loss logging
  - Per-step and per-epoch metrics logged to MLflow for fine-grained experiment comparison
  - Foundation for Module 3 (LoRA/PEFT) which requires direct access to the optimiser

MLflow experiment: "paraiq_pytorch_training"
Model saved to:   models/legal_classifier_pytorch/

Usage (from repo root, with venv active):
    python -m backend.demo1.mlops.pytorch_trainer

Or trigger via FastAPI endpoint:
    POST /model/pytorch-train
"""

import os
import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from torch.optim.lr_scheduler import LinearLR

import mlflow

log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
MODEL_DIR   = Path("models/legal_classifier_pytorch")
MLFLOW_URI  = os.environ.get(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{Path(__file__).parent.parent.parent.parent / 'mlflow.db'}"
)

# ── Label map (same as fine_tune.py) ──────────────────────────────────────────
LABEL_MAP   = {"PROSECUTION_FAVORABLE": 0, "DEFENSE_FAVORABLE": 1, "NEUTRAL": 2}
ID_TO_LABEL = {v: k for k, v in LABEL_MAP.items()}

# ── Training data (imported from fine_tune.py to stay DRY) ────────────────────
from backend.demo1.fine_tune import TRAINING_DATA


# ── Dataset ────────────────────────────────────────────────────────────────────

class LegalDataset(Dataset):
    """Tokenised legal sentence dataset for PyTorch DataLoader."""

    def __init__(self, texts: list[str], labels: list[int], tokenizer, max_len: int = 128):
        self.encodings = tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=max_len,
            return_tensors="pt",
        )
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return {
            "input_ids":      self.encodings["input_ids"][idx],
            "attention_mask": self.encodings["attention_mask"][idx],
            "labels":         self.labels[idx],
        }


# ── Metrics helpers ────────────────────────────────────────────────────────────

def accuracy(preds: torch.Tensor, labels: torch.Tensor) -> float:
    return (preds.argmax(dim=-1) == labels).float().mean().item()


def per_class_f1(preds: torch.Tensor, labels: torch.Tensor, num_classes: int = 3) -> dict:
    """Compute per-class F1 and macro-average without sklearn dependency at runtime."""
    pred_ids = preds.argmax(dim=-1)
    f1s = {}
    for c in range(num_classes):
        tp = ((pred_ids == c) & (labels == c)).sum().float()
        fp = ((pred_ids == c) & (labels != c)).sum().float()
        fn = ((pred_ids != c) & (labels == c)).sum().float()
        prec = tp / (tp + fp + 1e-8)
        rec  = tp / (tp + fn + 1e-8)
        f1s[ID_TO_LABEL[c]] = round((2 * prec * rec / (prec + rec + 1e-8)).item(), 4)
    f1s["macro_avg"] = round(sum(f1s.values()) / num_classes, 4)
    return f1s


# ── Training loop ──────────────────────────────────────────────────────────────

def train(
    epochs:     int   = 5,
    batch_size: int   = 8,
    lr:         float = 2e-5,
    seed:       int   = 42,
) -> dict:
    """
    Raw PyTorch training loop for legal sentence classifier.

    Logs per-epoch train_loss, val_loss, val_accuracy, val_f1_macro to MLflow.
    Saves best checkpoint (by val_accuracy) to MODEL_DIR.

    Returns final metrics dict.
    """
    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"[PyTorchTrainer] device={device}, epochs={epochs}, lr={lr}")

    # ── Load tokenizer + model ─────────────────────────────────────────────────
    from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

    log.info("[PyTorchTrainer] Loading DistilBERT tokenizer...")
    tokenizer = DistilBertTokenizerFast.from_pretrained("distilbert-base-uncased")

    log.info("[PyTorchTrainer] Loading DistilBERT model (3 labels)...")
    model = DistilBertForSequenceClassification.from_pretrained(
        "distilbert-base-uncased",
        num_labels=3,
        id2label=ID_TO_LABEL,
        label2id=LABEL_MAP,
    ).to(device)

    # ── Split data ─────────────────────────────────────────────────────────────
    from sklearn.model_selection import train_test_split
    texts  = [t for t, _ in TRAINING_DATA]
    labels = [LABEL_MAP[l] for _, l in TRAINING_DATA]
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=seed, stratify=labels
    )

    train_ds = LegalDataset(train_texts, train_labels, tokenizer)
    val_ds   = LegalDataset(val_texts,   val_labels,   tokenizer)
    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_dl   = DataLoader(val_ds,   batch_size=batch_size, shuffle=False)

    # ── Optimiser + scheduler ──────────────────────────────────────────────────
    optimiser = AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    total_steps = len(train_dl) * epochs
    scheduler = LinearLR(optimiser, start_factor=1.0, end_factor=0.1, total_iters=total_steps)

    # ── MLflow run ─────────────────────────────────────────────────────────────
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment("paraiq_pytorch_training")

    best_acc   = 0.0
    best_epoch = 0
    final_metrics = {}

    with mlflow.start_run(run_name=f"distilbert_e{epochs}_lr{lr}") as run:
        mlflow.log_params({
            "model":       "distilbert-base-uncased",
            "epochs":      epochs,
            "batch_size":  batch_size,
            "lr":          lr,
            "train_size":  len(train_texts),
            "val_size":    len(val_texts),
            "device":      str(device),
            "seed":        seed,
            "optimizer":   "AdamW",
            "scheduler":   "LinearLR",
        })

        t_start = time.time()

        for epoch in range(1, epochs + 1):
            # ── Train epoch ────────────────────────────────────────────────────
            model.train()
            epoch_loss = 0.0
            epoch_steps = 0

            for batch in train_dl:
                input_ids      = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                labels_batch   = batch["labels"].to(device)

                optimiser.zero_grad()
                outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels_batch)
                loss    = outputs.loss
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimiser.step()
                scheduler.step()

                epoch_loss  += loss.item()
                epoch_steps += 1

            train_loss = epoch_loss / epoch_steps

            # ── Validation ─────────────────────────────────────────────────────
            model.eval()
            all_logits = []
            all_labels = []
            val_loss_total = 0.0
            val_steps = 0

            with torch.no_grad():
                for batch in val_dl:
                    input_ids      = batch["input_ids"].to(device)
                    attention_mask = batch["attention_mask"].to(device)
                    labels_batch   = batch["labels"].to(device)

                    outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels_batch)
                    val_loss_total += outputs.loss.item()
                    val_steps += 1
                    all_logits.append(outputs.logits.cpu())
                    all_labels.append(labels_batch.cpu())

            val_loss = val_loss_total / val_steps
            logits_cat = torch.cat(all_logits)
            labels_cat = torch.cat(all_labels)
            val_acc = accuracy(logits_cat, labels_cat)
            f1s     = per_class_f1(logits_cat, labels_cat)

            current_lr = scheduler.get_last_lr()[0]

            # ── Log to MLflow per epoch ────────────────────────────────────────
            mlflow.log_metrics({
                "train_loss":   round(train_loss, 4),
                "val_loss":     round(val_loss, 4),
                "val_accuracy": round(val_acc, 4),
                "val_f1_macro": f1s["macro_avg"],
                "learning_rate": round(current_lr, 8),
                **{f"f1_{k.lower()[:4]}": v for k, v in f1s.items() if k != "macro_avg"},
            }, step=epoch)

            log.info(
                f"[PyTorchTrainer] Epoch {epoch}/{epochs} — "
                f"train_loss={train_loss:.4f}  val_loss={val_loss:.4f}  "
                f"val_acc={val_acc:.3f}  f1_macro={f1s['macro_avg']:.3f}"
            )

            # ── Save best checkpoint ───────────────────────────────────────────
            if val_acc > best_acc:
                best_acc   = val_acc
                best_epoch = epoch
                MODEL_DIR.mkdir(parents=True, exist_ok=True)
                model.save_pretrained(str(MODEL_DIR))
                tokenizer.save_pretrained(str(MODEL_DIR))
                log.info(f"[PyTorchTrainer] ✓ New best checkpoint saved (acc={best_acc:.3f})")

        elapsed = round(time.time() - t_start, 1)

        final_metrics = {
            "val_accuracy":   round(best_acc, 4),
            "val_f1_macro":   f1s["macro_avg"],
            "best_epoch":     best_epoch,
            "total_epochs":   epochs,
            "elapsed_s":      elapsed,
            "train_size":     len(train_texts),
            "val_size":       len(val_texts),
            "run_id":         run.info.run_id,
        }

        mlflow.log_metrics({
            "best_val_accuracy": round(best_acc, 4),
            "best_epoch":        best_epoch,
            "elapsed_s":         elapsed,
        })

    # ── Save metadata ──────────────────────────────────────────────────────────
    meta = {
        "model":        "distilbert-base-uncased",
        "task":         "legal-sentiment-classification",
        "trainer":      "pytorch_raw_loop",
        "labels":       list(LABEL_MAP.keys()),
        "train_size":   len(train_texts),
        "val_size":     len(val_texts),
        "epochs":       epochs,
        "best_epoch":   best_epoch,
        "accuracy":     round(best_acc, 4),
        "f1_macro":     f1s["macro_avg"],
        "elapsed_s":    elapsed,
        "trained_at":   datetime.now(timezone.utc).isoformat(),
        "mlflow_run_id": run.info.run_id,
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_DIR / "training_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    log.info(
        f"[PyTorchTrainer] Complete — best_acc={best_acc:.3f} @ epoch {best_epoch}, "
        f"elapsed={elapsed}s, run_id={run.info.run_id}"
    )
    return final_metrics


# ── Standalone entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    results = train(epochs=5, batch_size=8, lr=2e-5)
    print("\n=== Training Complete ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
