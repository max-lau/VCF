"""
A/B test report — analyzes JSONL log and prints comparison table.
Run with: cd /root/nlp-portfolio && .venv/bin/python3 scripts/ab_test_report.py
"""
import json, argparse, statistics
from collections import defaultdict

LOG_FILE = "/root/nlp-portfolio/logs/ab_test_log.jsonl"

def load_results(experiment_id: str):
    results = defaultdict(list)
    try:
        with open(LOG_FILE) as f:
            for line in f:
                r = json.loads(line)
                if r["experiment_id"] == experiment_id:
                    results[r["variant"]].append(r)
    except FileNotFoundError:
        print(f"No log file yet at {LOG_FILE}")
    return results

def report(experiment_id: str):
    results = load_results(experiment_id)
    if not results:
        print(f"No data for experiment: {experiment_id}")
        return
    variants = ["control", "variant_a", "variant_b"]
    print(f"\n=== A/B Test Report: {experiment_id} ===\n")
    print(f"  {'Metric':<28} {'Control':>10} {'Variant A':>10} {'Variant B':>10}")
    print(f"  {'-'*28} {'-'*10} {'-'*10} {'-'*10}")
    metrics = {
        "Sample size":        lambda r: len(r),
        "Avg latency (ms)":   lambda r: round(statistics.mean(x["latency_ms"] for x in r), 0),
        "Avg input tokens":   lambda r: round(statistics.mean(x["input_tokens"] for x in r), 0),
        "Avg output tokens":  lambda r: round(statistics.mean(x["output_tokens"] for x in r), 0),
        "Avg output length":  lambda r: round(statistics.mean(x["output_length"] for x in r), 0),
        "Total cost ($)":     lambda r: round(sum(
            x["input_tokens"]*0.000003 + x["output_tokens"]*0.000015 for x in r), 4),
    }
    for metric_name, fn in metrics.items():
        row = f"  {metric_name:<28}"
        for v in variants:
            data = results.get(v, [])
            try:
                val = fn(data) if data else "N/A"
            except Exception:
                val = "N/A"
            row += f" {str(val):>10}"
        print(row)
    print()
    print("  --- Interpretation ---")
    for v in variants:
        data = results.get(v, [])
        if data:
            avg_out = statistics.mean(x["output_tokens"] for x in data)
            avg_lat = statistics.mean(x["latency_ms"] for x in data)
            print(f"  {v}: n={len(data)}, avg_output_tokens={avg_out:.0f}, avg_latency={avg_lat:.0f}ms")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="case_brief_prompt_v1")
    args = parser.parse_args()
    report(args.experiment)
