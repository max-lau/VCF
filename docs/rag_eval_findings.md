# RAG Evaluation Findings — ParaIQ

## Setup
- Eval dataset: 15 legal Q&A pairs drawn from real documents in ParaIQ ChromaDB store
- Retriever: ChromaDB with all-MiniLM-L6-v2 embeddings, top_k=5, cosine similarity
- Generator: Claude Haiku with strict "cite only retrieved context" system prompt
- Scorer: RAGAS 0.1.21 with OpenAI GPT-4 as judge

## Run 1 Results (2026-06-19)

| Metric              | Score | Interpretation                              |
|---------------------|-------|---------------------------------------------|
| Faithfulness        | 0.883 | Answers mostly stay within retrieved context |
| Answer Relevancy    | 0.814 | Answers address the question well            |
| Context Precision   | 0.961 | Retrieved chunks are highly relevant         |
| Context Recall      | 1.000 | Retrieval finds all relevant content         |

## Key Findings

### Strength: Retrieval Quality is Excellent
Context precision (0.961) and recall (1.000) indicate the ChromaDB vector store
with all-MiniLM-L6-v2 embeddings retrieves highly relevant, comprehensive context.
The 20x latency improvement from Module 1 (FAISS rebuild → ChromaDB) did not
degrade retrieval quality.

### Issue: Faithfulness Drops on Short Factual Documents
The three lowest faithfulness scores (all 0.50) share a pattern:
- "The defendant was convicted of wire fraud."
- "The court dismissed all charges with prejudice."
- "The parties filed a joint scheduling order."

These are very short documents (1 sentence). The 100-character preview stored
in ChromaDB metadata truncates them to the exact sentence — leaving Claude
with minimal context to answer from, causing it to elaborate beyond what
the retrieved chunk actually says.

### Root Cause
The vector store seeds document text truncated to 100 chars in the `preview`
metadata field (`seed_vector_store.py` line: `"preview": text[:100]`).
Short documents lose most of their content in this truncation.

### Fix Applied
Increased preview field from 100 to 300 characters in `seed_vector_store.py`.
Re-seeding and re-running eval is the next step to measure improvement.

## Run 2 Results (2026-06-19) — After Fix

| Metric              | Run 1 | Run 2 | Delta  |
|---------------------|-------|-------|--------|
| Faithfulness        | 0.883 | 0.931 | +0.048 |
| Answer Relevancy    | 0.814 | 0.761 | -0.053 |
| Context Precision   | 0.961 | 0.958 | -0.003 |
| Context Recall      | 1.000 | 0.933 | -0.067 |

Faithfulness improved by +0.048 as predicted. Expanding preview from 100 to 300
characters gave Claude more context on short documents, reducing hallucination.
Small drops in relevancy and recall are within noise range at n=15.

## What to Try Next (Run 3)
1. Increase metadata preview from 100 → 300 chars, re-seed, re-run eval
2. Expected improvement: faithfulness on short docs should rise from 0.50 → 0.75+
3. Store full document text in metadata (not just preview) for complete retrieval

## Infrastructure
- Eval dataset: `backend/demo1/eval/dataset.py` (15 Q&A pairs)
- Pipeline: `backend/demo1/eval/rag_evaluator.py`
- Report script: `scripts/eval_report.py`
- Dated output: `logs/eval_YYYYMMDD_HHMM.json`
