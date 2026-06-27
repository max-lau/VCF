"""
backend/demo1/mlops/registry.py
================================
ParaIQ Model Registry — MLflow model versioning for legal classifiers.

Usage:
    from backend.demo1.mlops.registry import register_model, get_latest_model_version
    
    # Register after training
    version = register_model(
        model_path="models/legal_classifier",
        model_name="paraiq-legal-classifier",
        metrics={"accuracy": 0.87, "f1": 0.85},
        tags={"task": "legal-sentiment", "train_size": 480},
    )
"""
import os
import json
import mlflow
import mlflow.pyfunc
from pathlib import Path
from datetime import datetime, timezone

MLFLOW_URI  = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5050")
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def register_model(
    model_path:  str,
    model_name:  str = "paraiq-legal-classifier",
    metrics:     dict = None,
    tags:        dict = None,
    description: str = None,
) -> str:
    """
    Register a trained model in the MLflow Model Registry.
    Returns the version string.
    """
    mlflow.set_tracking_uri(MLFLOW_URI)

    abs_path = Path(model_path) if Path(model_path).is_absolute() else PROJECT_ROOT / model_path

    # Read training_meta.json if present
    meta_path = abs_path / "training_meta.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())

    all_metrics = {
        "accuracy":   meta.get("accuracy", 0.0),
        "f1_score":   meta.get("f1_score", 0.0),
        "train_size": float(meta.get("train_size", 0)),
        "val_size":   float(meta.get("val_size", 0)),
        "epochs":     float(meta.get("epochs", 0)),
    }
    if metrics:
        all_metrics.update(metrics)

    all_tags = {
        "task":        meta.get("task", "unknown"),
        "base_model":  meta.get("model", "unknown"),
        "labels":      str(meta.get("labels", [])),
        "trained_at":  meta.get("trained_at", "unknown"),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    if tags:
        all_tags.update(tags)

    mlflow.set_experiment("paraiq_model_registry")

    with mlflow.start_run(tags=all_tags) as run:
        mlflow.log_metrics(all_metrics)
        mlflow.log_params({
            "model_path": str(abs_path),
            "model_name": model_name,
            "base_model": meta.get("model", "unknown"),
            "num_labels": len(meta.get("labels", [])),
        })

        # Log model artifacts
        if abs_path.exists():
            mlflow.log_artifacts(str(abs_path), artifact_path="model")

        # Register in Model Registry using artifact path
        model_uri = f"runs:/{run.info.run_id}/model"
        client = mlflow.MlflowClient()
        mv = client.create_model_version(
            name=model_name,
            source=model_uri,
            run_id=run.info.run_id,
        )

        if description:
            client = mlflow.MlflowClient()
            client.update_model_version(
                name=model_name,
                version=mv.version,
                description=description,
            )

        print(f"[Registry] Registered {model_name} v{mv.version} — run {run.info.run_id}")
        return mv.version


def get_latest_model_version(model_name: str = "paraiq-legal-classifier") -> dict:
    """Return metadata about the latest registered version."""
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = mlflow.MlflowClient()
    try:
        versions = client.search_model_versions(f"name='{model_name}'")
        if not versions:
            return {"error": f"No versions found for {model_name}"}
        latest = sorted(versions, key=lambda v: int(v.version), reverse=True)[0]
        return {
            "model_name":  latest.name,
            "version":     latest.version,
            "status":      latest.status,
            "run_id":      latest.run_id,
            "source":      latest.source,
            "created_at":  latest.creation_timestamp,
        }
    except Exception as e:
        return {"error": "Internal error occurred"}


def list_model_versions(model_name: str = "paraiq-legal-classifier") -> list:
    """List all registered versions with their metrics."""
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = mlflow.MlflowClient()
    try:
        versions = client.search_model_versions(f"name='{model_name}'")
        results = []
        for v in sorted(versions, key=lambda x: int(x.version)):
            run = client.get_run(v.run_id)
            results.append({
                "version":  v.version,
                "status":   v.status,
                "accuracy": run.data.metrics.get("accuracy", 0),
                "f1_score": run.data.metrics.get("f1_score", 0),
                "train_size": int(run.data.metrics.get("train_size", 0)),
                "trained_at": run.data.tags.get("trained_at", "unknown"),
            })
        return results
    except Exception as e:
        return [{"error": "Internal error occurred"}]
