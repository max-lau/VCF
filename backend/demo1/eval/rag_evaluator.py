"""
ParaIQ RAG Evaluation Pipeline using RAGAS 0.1.x.
Measures faithfulness, answer relevancy, context precision, context recall.
Run with: cd /root/nlp-portfolio && .venv/bin/python3 scripts/eval_report.py
"""
import os, sys, json
sys.path.insert(0, "/root/nlp-portfolio")
from dotenv import load_dotenv
load_dotenv("/root/nlp-portfolio/.env")

from sentence_transformers import SentenceTransformer
from backend.demo1.retrieval.factory import get_vector_store
from backend.demo1.eval.dataset import EVAL_DATASET
from backend.demo1.ai_client import get_client as _get_client

_embedder = None
_client = None

def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder

def get_client():
    global _client
    if _client is None:
        _client = _get_client()
    return _client

def retrieve(question: str, top_k: int = 5):
    """Retrieve top_k relevant chunks from ChromaDB for a question."""
    store = get_vector_store(collection="paraiq_entities")
    embedder = get_embedder()
    vec = embedder.encode([question], convert_to_numpy=True)[0].tolist()
    results = store.query(vec, top_k=top_k)
    contexts = []
    for doc_id, distance, meta in results:
        # Run 3: prefer full_text; fall back to preview for backward compat
        text = meta.get("full_text") or meta.get("preview", "")
        if text:
            contexts.append(text)
    return contexts

def generate_answer(question: str, contexts: list) -> str:
    """Generate answer from Claude using retrieved contexts."""
    ctx_text = "\n".join(f"- {c}" for c in contexts)
    prompt = (
        "You are a legal research assistant. Answer the question using ONLY "
        "the provided context. If the context does not contain the answer, "
        "say: The context does not contain enough information to answer this question.\n\n"
        f"Context:\n{ctx_text}\n\nQuestion: {question}\n\nAnswer:"
    )
    client = get_client()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()

def run_paraiq_rag(item: dict) -> dict:
    """Run full RAG pipeline for one eval item."""
    question = item["question"]
    contexts = retrieve(question, top_k=5)
    answer   = generate_answer(question, contexts)
    return {"answer": answer, "contexts": contexts}

def build_ragas_dataset():
    """Run RAG pipeline over all eval items and collect results."""
    from datasets import Dataset
    questions, answers, contexts, ground_truths = [], [], [], []
    print(f"Running RAG pipeline over {len(EVAL_DATASET)} eval questions...")
    for i, item in enumerate(EVAL_DATASET):
        print(f"  [{i+1}/{len(EVAL_DATASET)}] {item['question'][:60]}...")
        result = run_paraiq_rag(item)
        questions.append(item["question"])
        answers.append(result["answer"])
        contexts.append(result["contexts"])
        ground_truths.append(item["ground_truth"])
    return Dataset.from_dict({
        "question":     questions,
        "answer":       answers,
        "contexts":     contexts,
        "ground_truth": ground_truths,
    })

def evaluate_paraiq():
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    dataset = build_ragas_dataset()
    print("\nRunning RAGAS evaluation (uses OpenAI)...")
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )
    return result
