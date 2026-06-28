"""
semantic_search.py
==================
ParaIQ — Semantic search across case documents using vector embeddings.

Uses the existing ChromaDB vector store + all-MiniLM-L6-v2 embedder
to find documents by meaning, not just keyword match.

Endpoints:
  POST /search/semantic        — search across all cases in the firm
  POST /search/semantic/{cid}  — search within a specific case
  GET  /search/status          — index stats (doc count, last updated)
  POST /search/index           — re-index a case's documents into ChromaDB
"""
import os
import json
import logging
import asyncio
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Depends, Query

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_user, get_current_firm_id

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Lazy-loaded embedder (avoids loading model at import time) ───────────────
_EMBEDDER = None
_EMBEDDER_LOCK = asyncio.Lock()


async def _get_embedder():
    """Lazily load the MiniLM sentence transformer (384-dim)."""
    global _EMBEDDER
    if _EMBEDDER is None:
        async with _EMBEDDER_LOCK:
            if _EMBEDDER is None:
                from sentence_transformers import SentenceTransformer
                _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("[SemanticSearch] MiniLM embedder loaded (384-dim)")
    return _EMBEDDER


def _get_store():
    """Get the ChromaDB vector store for document search."""
    from backend.demo1.retrieval.factory import get_vector_store
    return get_vector_store(collection="paraiq_docs")


# ── Models ────────────────────────────────────────────────────────────────────

class SemanticSearchRequest(BaseModel):
    query: str
    case_id: Optional[int] = None
    top_k: int = 10
    min_score: float = 0.3  # cosine similarity threshold (0-1, higher = better)


class IndexRequest(BaseModel):
    case_id: int
    force: bool = False  # re-index even if already indexed


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk_text(text: str, max_chars: int = 1000, overlap: int = 100) -> List[str]:
    """Split long documents into overlapping chunks for better retrieval."""
    if not text or len(text) <= max_chars:
        return [text] if text else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        # Try to break at a sentence boundary
        if end < len(text):
            last_period = text.rfind(". ", start, end)
            if last_period > start + max_chars // 2:
                end = last_period + 1
        chunks.append(text[start:end].strip())
        start = end - overlap
    return chunks


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert a psycopg2 RealDictRow to a plain dict."""
    return dict(row) if hasattr(row, "keys") else dict(row._mapping)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/semantic")
async def semantic_search(
    req: SemanticSearchRequest,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """
    Search across all case documents by meaning.

    Embeds the query and searches the ChromaDB vector store,
    then joins results with Postgres to get document names, case info, and snippets.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(400, "Query text is required")
    if req.top_k < 1 or req.top_k > 50:
        raise HTTPException(400, "top_k must be between 1 and 50")

    try:
        embedder = await _get_embedder()
        query_embedding = embedder.encode(req.query.strip()).tolist()
    except Exception as e:
        logger.error(f"[SemanticSearch] Embedding failed: {e}")
        raise HTTPException(500, "Search embedding failed. Please try again.")

    try:
        store = _get_store()
        # Search more than needed so we can filter by score + firm
        raw_results = store.query(query_embedding, top_k=req.top_k * 3)
    except Exception as e:
        logger.error(f"[SemanticSearch] Vector store query failed: {e}")
        raise HTTPException(500, "Search index query failed. Please try again.")

    if not raw_results:
        return {"query": req.query, "results": [], "count": 0}

    # Filter by minimum similarity score (ChromaDB returns cosine distance 0-2,
    # where 0 = identical. Convert to similarity: 1 - distance/2)
    filtered = []
    for doc_id, distance, metadata in raw_results:
        similarity = 1.0 - (distance / 2.0)
        if similarity < req.min_score:
            continue
        # Filter by firm_id for tenant isolation
        if metadata.get("firm_id") != firm_id:
            continue
        # Filter by case_id if specified
        if req.case_id and metadata.get("case_id") != str(req.case_id):
            continue
        filtered.append({
            "doc_id": doc_id,
            "score": round(similarity, 4),
            "metadata": metadata,
        })

    if not filtered:
        return {"query": req.query, "results": [], "count": 0}

    # Enrich with document + case info from Postgres
    doc_ids = [r["doc_id"] for r in filtered]
    enriched = []

    try:
        with get_conn(firm_id) as conn:
            # Build placeholders for IN clause
            placeholders = ",".join(["%s"] * len(doc_ids))
            rows = conn.execute(
                f"""
                SELECT cd.id, cd.document_name, cd.source, cd.case_id,
                       cd.doc_text, cd.risk_level, cd.risk_score,
                       c.case_number, c.client_name, c.matter_number,
                       c.court, c.status
                FROM case_documents cd
                JOIN cases c ON c.id = cd.case_id
                WHERE cd.id IN ({placeholders})
                  AND cd.firm_id = %s
                """,
                (*doc_ids, firm_id)
            ).fetchall()

            row_map = {str(r["id"]): _row_to_dict(r) for r in rows} if rows else {}

            for result in filtered:
                doc_info = row_map.get(result["doc_id"])
                if not doc_info:
                    continue

                # Extract snippet around the most relevant part
                doc_text = doc_info.get("doc_text") or ""
                snippet = _extract_snippet(req.query.lower(), doc_text, 200)

                enriched.append({
                    "doc_id": int(result["doc_id"]),
                    "document_name": doc_info.get("document_name", ""),
                    "source": doc_info.get("source", ""),
                    "case_id": doc_info.get("case_id"),
                    "case_number": doc_info.get("case_number", ""),
                    "client_name": doc_info.get("client_name", ""),
                    "matter_number": doc_info.get("matter_number", ""),
                    "court": doc_info.get("court", ""),
                    "case_status": doc_info.get("status", ""),
                    "risk_level": doc_info.get("risk_level", ""),
                    "score": result["score"],
                    "snippet": snippet,
                })

        # Re-sort by score descending (enrichment may have reordered)
        enriched.sort(key=lambda x: x["score"], reverse=True)
        enriched = enriched[:req.top_k]

    except Exception as e:
        logger.error(f"[SemanticSearch] Enrichment query failed: {e}")
        raise HTTPException(500, "Search result enrichment failed. Please try again.")

    return {
        "query": req.query,
        "results": enriched,
        "count": len(enriched),
    }


@router.post("/semantic/{case_id}")
async def semantic_search_in_case(
    case_id: int,
    req: SemanticSearchRequest,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Search within a specific case's documents."""
    req.case_id = case_id
    return await semantic_search(req, firm_id=firm_id, current_user=current_user)


@router.get("/status")
async def search_index_status(
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Return the current state of the semantic search index."""
    try:
        store = _get_store()
        total = store.count()
    except Exception as e:
        logger.warning(f"[SemanticSearch] Could not get index count: {e}")
        total = 0

    # Count how many are in this firm
    firm_count = 0
    try:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM case_documents WHERE firm_id = %s AND doc_text IS NOT NULL",
                (firm_id,)
            ).fetchone()
            firm_count = row["n"] if row else 0
    except Exception:
        pass

    return {
        "index_total": total,
        "firm_documents": firm_count,
        "indexed": "unknown",  # would need to query ChromaDB metadata
    }


@router.post("/index")
async def index_case_documents(
    req: IndexRequest,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """
    Index (or re-index) a case's documents into the vector store.

    Splits each document into chunks, embeds them, and upserts into ChromaDB.
    """
    try:
        with get_conn(firm_id) as conn:
            rows = conn.execute(
                """
                SELECT id, case_id, document_name, doc_text
                FROM case_documents
                WHERE case_id = %s AND firm_id = %s AND doc_text IS NOT NULL
                """,
                (req.case_id, firm_id)
            ).fetchall()

            if not rows:
                return {"success": True, "indexed": 0, "message": "No documents found to index"}

            embedder = await _get_embedder()
            store = _get_store()

            total_chunks = 0
            for row in rows:
                doc_id = str(row["id"])
                doc_text = row["doc_text"] or ""
                chunks = _chunk_text(doc_text)

                for i, chunk in enumerate(chunks):
                    chunk_id = f"{doc_id}_chunk_{i}"
                    embedding = embedder.encode(chunk).tolist()

                    store.upsert(
                        doc_id=chunk_id,
                        embedding=embedding,
                        metadata={
                            "firm_id": firm_id,
                            "case_id": str(row["case_id"]),
                            "document_id": doc_id,
                            "document_name": row["document_name"],
                            "chunk_index": str(i),
                            "chunk_text": chunk[:500],  # store preview (metadata limit)
                        }
                    )
                    total_chunks += 1

            return {
                "success": True,
                "documents_indexed": len(rows),
                "chunks_created": total_chunks,
                "case_id": req.case_id,
            }

    except Exception as e:
        logger.error(f"[SemanticSearch] Indexing failed for case {req.case_id}: {e}")
        raise HTTPException(500, f"Indexing failed: {e}")


# ── Utility ──────────────────────────────────────────────────────────────────

def _extract_snippet(query_lower: str, text: str, max_len: int = 200) -> str:
    """Extract the most relevant snippet from a document for display."""
    if not text:
        return ""

    text_lower = text.lower()

    # Find the first query word that appears in the text
    query_words = [w for w in query_lower.split() if len(w) > 2]
    best_pos = -1
    for word in query_words:
        pos = text_lower.find(word)
        if pos >= 0:
            best_pos = pos
            break

    if best_pos < 0:
        # No keyword match — return the beginning
        return text[:max_len].strip() + ("..." if len(text) > max_len else "")

    # Extract context around the match
    start = max(0, best_pos - max_len // 3)
    end = min(len(text), start + max_len)

    snippet = text[start:end].strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"
