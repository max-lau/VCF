"""
Cross-document entity linking.
find_linked_entities: uses persisted ChromaDB vector store (swappable via VECTOR_BACKEND).
link_documents_by_entity: uses in-memory FAISS for pairwise doc comparison (stateless, kept as-is).
"""
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from backend.demo1.database import get_connection
from backend.demo1.retrieval.factory import get_vector_store
from typing import List, Dict

_EMBEDDER = None

def get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        print("Loading sentence transformer model...")
        _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
        print("Model loaded.")
    return _EMBEDDER

def get_all_entities() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, entities, text, created_at, sentiment FROM analyses"
    ).fetchall()
    conn.close()
    all_entities = []
    for row in rows:
        try:
            entities = json.loads(row["entities"] or "[]")
            for ent in entities:
                all_entities.append({
                    "analysis_id":   row["id"],
                    "text":          ent.get("text", ""),
                    "type":          ent.get("type", "OTHER"),
                    "doc_preview":   row["text"][:100],
                    "doc_sentiment": row["sentiment"],
                    "created_at":    row["created_at"]
                })
        except Exception:
            continue
    return all_entities

def find_linked_entities(query_entity: str, top_k: int = 5,
                          threshold: float = 0.75) -> List[Dict]:
    """
    Find entities semantically similar to query_entity across all documents.
    Uses persisted ChromaDB index (or Pinecone if VECTOR_BACKEND=pinecone).
    Replaces the previous pattern that rebuilt a FAISS index on every call.
    """
    embedder  = get_embedder()
    store     = get_vector_store(collection="paraiq_entities")

    if store.count() == 0:
        return []

    query_vec = embedder.encode([query_entity], convert_to_numpy=True)[0].tolist()
    raw       = store.query(query_vec, top_k=top_k + 1)

    # ChromaDB cosine distance: 0 = identical, 2 = opposite
    # Convert to similarity score: 1 - (distance / 2), filter by threshold
    results    = []
    seen_texts = set()
    for doc_id, distance, meta in raw:
        similarity = 1.0 - (distance / 2.0)
        if similarity < threshold:
            continue
        preview = meta.get("preview", "")
        if preview.lower() == query_entity.lower():
            continue
        if preview.lower() in seen_texts:
            continue
        seen_texts.add(preview.lower())
        results.append({
            "entity":        preview[:80],
            "type":          meta.get("type", "DOCUMENT"),
            "similarity":    round(similarity, 4),
            "analysis_id":   meta.get("analysis_id", ""),
            "doc_preview":   preview,
            "doc_sentiment": meta.get("sentiment", ""),
            "created_at":    meta.get("created_at", "")
        })
    return results

def link_documents_by_entity(min_shared: int = 1) -> List[Dict]:
    all_entities = get_all_entities()
    if not all_entities:
        return []

    doc_entities = {}
    for e in all_entities:
        aid = e["analysis_id"]
        if aid not in doc_entities:
            doc_entities[aid] = {
                "analysis_id": aid,
                "doc_preview": e["doc_preview"],
                "entities":    []
            }
        doc_entities[aid]["entities"].append(e["text"])

    docs = list(doc_entities.values())
    if len(docs) < 2:
        return []

    embedder = get_embedder()
    doc_vecs = []
    for doc in docs:
        ent_texts = doc["entities"]
        if not ent_texts:
            doc_vecs.append(np.zeros(384))
            continue
        vecs = embedder.encode(ent_texts, convert_to_numpy=True)
        avg  = vecs.mean(axis=0)
        avg  = avg / (np.linalg.norm(avg) + 1e-10)
        doc_vecs.append(avg)

    doc_vecs = np.array(doc_vecs, dtype=np.float32)

    pairs = []
    for i in range(len(docs)):
        for j in range(i+1, len(docs)):
            sim = float(np.dot(doc_vecs[i], doc_vecs[j]))
            if sim > 0.5:
                set_i  = set(e.lower() for e in docs[i]["entities"])
                set_j  = set(e.lower() for e in docs[j]["entities"])
                shared = list(set_i & set_j)
                pairs.append({
                    "doc_a_id":        docs[i]["analysis_id"],
                    "doc_a_preview":   docs[i]["doc_preview"],
                    "doc_b_id":        docs[j]["analysis_id"],
                    "doc_b_preview":   docs[j]["doc_preview"],
                    "similarity":      round(sim, 4),
                    "shared_entities": shared[:5]
                })

    pairs.sort(key=lambda x: x["similarity"], reverse=True)
    return pairs[:10]
