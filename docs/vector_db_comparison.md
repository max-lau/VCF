# Vector DB Comparison: In-Memory FAISS vs ChromaDB vs Pinecone

## Context

ParaIQ originally used in-memory FAISS in `contradiction.py` and `entity_linker.py`.
Both files rebuilt the full index on every request — loading all documents from the
database, re-encoding them, and discarding the index after each call. This worked
at small scale but had two fundamental problems:

1. **No persistence** — index reset on every request; no incremental updates
2. **O(n) embedding cost per request** — encoding all 219 documents on every query

This document compares the three approaches evaluated for ParaIQ.

---

## Comparison Table

| Dimension              | In-Memory FAISS          | ChromaDB (persistent)         | Pinecone (serverless)          |
|------------------------|--------------------------|-------------------------------|--------------------------------|
| **Persistence**        | None — rebuilds per call | On-disk, survives restarts    | Managed cloud, always durable  |
| **Setup complexity**   | Zero (already installed) | pip install + local path      | API key + index creation       |
| **Query latency**      | ~820ms (219 docs, incl. encode) | ~39ms warm (pre-indexed) | ~80–120ms (network RTT, est.)  |
| **Incremental upsert** | Not supported            | Yes — O(1) per new doc        | Yes — O(1) per new doc         |
| **Multi-tenant**       | Not possible             | Possible via collection names | Native via namespaces          |
| **Operational burden** | None (in-process)        | Manage disk, backups          | Fully managed, zero ops        |
| **Cost**               | Free                     | Free (self-hosted)            | Free tier: 1 index, 100k vecs  |
| **Scale ceiling**      | ~10k docs before lag     | ~500k docs (single node)      | Billions of vectors            |
| **Embedding model**    | Caller manages           | Caller manages                | Caller manages                 |

---

## Latency Benchmark (ParaIQ VPS, 219 documents)

| Approach           | Cold query time | Warm query time |
|--------------------|----------------|----------------|
| In-memory FAISS    | ~820ms         | ~820ms (always cold — rebuilds every call) |
| ChromaDB persisted | ~2300ms (first load incl. model) | ~39ms        |
| Pinecone serverless| N/A (not benchmarked) | ~95ms est.  |

FAISS baseline measured by timing `find_similar_doc_pairs()` with 219 docs.
ChromaDB warm time measured via `store.query()` after index loaded from disk.

---

## When to Use Each

**In-memory FAISS**
- Prototyping and one-off scripts
- Datasets under ~1k documents where rebuild cost is acceptable
- No persistence requirement

**ChromaDB**
- Default for ParaIQ development and single-VPS deployment
- When you want persistence without external dependencies
- Good fit for up to ~500k vectors on a single node
- Self-hosted: you manage backups and disk

**Pinecone**
- Production multi-tenant at scale (ParaIQ Tier 2/3 deployment)
- When operational burden must be zero
- When you need sub-100ms queries across millions of vectors
- Activate in ParaIQ via `VECTOR_BACKEND=pinecone` in `.env`

---

## Migration

A one-time seed script migrates all existing analyses into the vector store:

```bash
# Seed ChromaDB (default)
python3 scripts/seed_vector_store.py

# Seed Pinecone
VECTOR_BACKEND=pinecone python3 scripts/seed_vector_store.py --backend pinecone
```

Subsequent document ingestion should call `store.upsert()` incrementally —
the rebuild-every-request pattern in `contradiction.py` and `entity_linker.py`
has been replaced with persisted queries against the pre-built index.

---

## Key Finding

The primary improvement from this migration is not raw query speed (FAISS is fast
in-memory) but **architectural correctness**: a retrieval system that rebuilds its
entire index on every request cannot support incremental updates, multi-tenancy,
or cross-restart consistency. ChromaDB provides all three with no external dependencies,
making it the right default for ParaIQ's current single-VPS deployment tier.
