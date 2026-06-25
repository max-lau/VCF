#!/bin/bash
cd /root/nlp-portfolio
exec .venv/bin/mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlflow-artifacts \
  --host 0.0.0.0 \
  --port 5050
