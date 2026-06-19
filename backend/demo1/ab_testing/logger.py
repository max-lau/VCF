"""
A/B test logger — appends JSONL records for each experiment result.
Log file: /root/nlp-portfolio/logs/ab_test_log.jsonl
"""
import json, os
from datetime import datetime, timezone
from backend.demo1.ab_testing.variants import PromptVariant

LOG_FILE = os.getenv("AB_LOG_FILE", "/root/nlp-portfolio/logs/ab_test_log.jsonl")

def log_experiment_result(
    experiment_id: str,
    case_id: int,
    variant: PromptVariant,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    output_text: str,
    trace_id: str = None,
):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    record = {
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "experiment_id": experiment_id,
        "case_id":       case_id,
        "variant":       variant.value,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "latency_ms":    round(latency_ms, 1),
        "output_length": len(output_text),
        "trace_id":      trace_id,
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")
