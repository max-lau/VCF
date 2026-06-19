"""
Seeds the ParaIQ vector store from existing analyses in the database.
Replaces the rebuild-every-request FAISS pattern with a persisted index.

Run with:
    cd /root/nlp-portfolio
    .venv/bin/python3 scripts/seed_vector_store.py [--dry-run] [--backend chroma|pinecone]
"""
import argparse
import sys
import os
sys.path.insert(0, '/root/nlp-portfolio')

from dotenv import load_dotenv
load_dotenv('/root/nlp-portfolio/.env')

from sentence_transformers import SentenceTransformer
from backend.demo1.retrieval.factory import get_vector_store
import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = os.getenv("DATABASE_URL")

def get_analyses():
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT id, text, entities, sentiment, created_at FROM analyses WHERE text IS NOT NULL AND text != ''")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows

def migrate(dry_run: bool, backend: str):
    print(f"{'[DRY RUN] ' if dry_run else ''}Seeding vector store (backend={backend})...")
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    store = get_vector_store(collection="paraiq_entities", backend=backend)
    rows = get_analyses()
    print(f"Found {len(rows)} analyses in database")
    seeded = 0
    for row in rows:
        doc_id = f"analysis_{row['id']}"
        text = (row['text'] or '')[:500]
        if not text.strip():
            continue
        embedding = embedder.encode([text], convert_to_numpy=True)[0].tolist()
        metadata = {
            "analysis_id": str(row['id']),
            "sentiment":   str(row['sentiment'] or ''),
            "preview":     text[:300],
            "created_at":  str(row['created_at'] or '')
        }
        if dry_run:
            print(f"  Would upsert: {doc_id} | {text[:60]}...")
        else:
            store.upsert(doc_id, embedding, metadata)
        seeded += 1
    print(f"{'Would seed' if dry_run else 'Seeded'} {seeded} documents -> {backend}")
    if not dry_run:
        print(f"Total vectors in store: {store.count()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backend", default="chroma", choices=["chroma", "pinecone"])
    args = parser.parse_args()
    migrate(dry_run=args.dry_run, backend=args.backend)
