"""
ParaIQ RAG Evaluation Report — runs RAGAS and saves scored output.
Run with: cd /root/nlp-portfolio && .venv/bin/python3 scripts/eval_report.py
"""
import sys, json, os
sys.path.insert(0, "/root/nlp-portfolio")
from dotenv import load_dotenv
load_dotenv("/root/nlp-portfolio/.env")
from datetime import datetime, timezone
from backend.demo1.eval.rag_evaluator import evaluate_paraiq

def generate_eval_report():
    results = evaluate_paraiq()
    scores  = results.to_pandas()
    report  = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": {
            "faithfulness":      float(scores["faithfulness"].mean()),
            "answer_relevancy":  float(scores["answer_relevancy"].mean()),
            "context_precision": float(scores["context_precision"].mean()),
            "context_recall":    float(scores["context_recall"].mean()),
        },
        "weakest": scores.nsmallest(3, "faithfulness")[
            ["question", "faithfulness", "context_precision"]
        ].to_dict(orient="records")
    }
    print("\n=== ParaIQ RAG Evaluation Results ===")
    for k, v in report["overall"].items():
        bar = "#" * int(v * 20)
        print(f"  {k:<22} {v:.3f}  [{bar:<20}]")
    print("\n  Weakest faithfulness:")
    for w in report["weakest"]:
        print(f'    {w["question"][:55]:<55} faith={w["faithfulness"]:.2f}  prec={w["context_precision"]:.2f}')
    os.makedirs("/root/nlp-portfolio/logs", exist_ok=True)
    fname = f"/root/nlp-portfolio/logs/eval_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(fname, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Saved: {fname}")
    print("\n  --- Interpretation ---")
    o = report["overall"]
    if o["faithfulness"] < 0.7:
        print("  WARNING faithfulness < 0.7: LLM may be hallucinating beyond context.")
        print("          Fix: stricter system prompt — cite only retrieved content.")
    if o["context_precision"] < 0.7:
        print("  WARNING context_precision < 0.7: retrieval pulling irrelevant chunks.")
        print("          Fix: smaller chunk size or higher similarity threshold.")
    if o["context_recall"] < 0.7:
        print("  WARNING context_recall < 0.7: retrieval missing relevant content.")
        print("          Fix: increase top_k or add keyword hybrid search.")
    return report

if __name__ == "__main__":
    generate_eval_report()
