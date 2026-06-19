"""
ParaIQ Observability Report — weekly cost and latency summary.
Queries Langfuse REST API directly (Langfuse 4.x removed Python fetch methods).
Run with: cd /root/nlp-portfolio && .venv/bin/python3 scripts/observability_report.py
"""
import os, sys, requests
sys.path.insert(0, "/root/nlp-portfolio")
from dotenv import load_dotenv
load_dotenv("/root/nlp-portfolio/.env")
from datetime import datetime, timedelta, timezone

PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.00000080, "output": 0.00000400},
    "claude-sonnet-4-20250514":  {"input": 0.00000300, "output": 0.00001500},
}

def estimate_cost(model, inp, out):
    p = PRICING.get(model, {"input": 0.000003, "output": 0.000015})
    return p["input"] * inp + p["output"] * out

def generate_report(days: int = 7):
    host   = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    key    = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret = os.getenv("LANGFUSE_SECRET_KEY")
    auth   = (key, secret)
    since  = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    total_cost, latencies, by_name, flagged = 0.0, [], {}, []
    page, limit = 1, 50

    print(f"Fetching observations from last {days} days...")
    while True:
        r = requests.get(
            f"{host}/api/public/observations",
            auth=auth,
            params={"limit": limit, "page": page, "fromStartTime": since}
        )
        r.raise_for_status()
        data = r.json()["data"]
        if not data:
            break
        for obs in data:
            name  = obs.get("name") or "unknown"
            model = obs.get("model") or "unknown"
            usage = obs.get("usage") or {}
            inp   = usage.get("input") or 0
            out   = usage.get("output") or 0
            cost  = estimate_cost(model, inp, out)
            total_cost += cost
            lat = obs.get("latency")
            if lat:
                latencies.append(lat)
            if name not in by_name:
                by_name[name] = {"count": 0, "cost": 0.0, "tokens_in": 0, "tokens_out": 0}
            by_name[name]["count"]      += 1
            by_name[name]["cost"]       += cost
            by_name[name]["tokens_in"]  += inp
            by_name[name]["tokens_out"] += out
            if obs.get("level") == "ERROR":
                flagged.append(obs.get("id"))
        if len(data) < limit:
            break
        page += 1

    total = sum(by_name[n]["count"] for n in by_name)
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    print()
    print(f"=== ParaIQ Observability Report (last {days} days) ===")
    print(f"  Total observations : {total}")
    print(f"  Estimated cost     : ${total_cost:.6f}")
    print(f"  Avg latency        : {avg_lat:.0f}ms")
    print(f"  Errored calls      : {len(flagged)}")
    print()
    print(f"  {"Call type":<35} {"calls":>6}  {"tok_in":>8}  {"tok_out":>8}  {"cost":>12}")
    print(f"  {"-"*35} {"------":>6}  {"--------":>8}  {"--------":>8}  {"-----------":>12}")
    for name, s in sorted(by_name.items(), key=lambda x: -x[1]["cost"]):
        print(f'  {name:<35} {s["count"]:>6}  {s["tokens_in"]:>8}  {s["tokens_out"]:>8}  ${s["cost"]:>11.6f}')

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    generate_report(days=args.days)
