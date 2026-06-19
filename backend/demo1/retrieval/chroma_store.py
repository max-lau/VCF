"""
ChromaDB persistent backend for ParaIQ vector store.
Replaces the rebuild-every-request FAISS pattern in contradiction.py
and entity_linker.py with a persisted, incrementally-updated index.
"""
import chromadb
from chromadb.config import Settings
from typing import List, Tuple, Dict
from .base import VectorStoreBase


class ChromaStore(VectorStoreBase):

    def __init__(self, collection_name: str, persist_dir: str = "/root/nlp-portfolio/chroma_db"):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, doc_id: str, embedding: List[float], metadata: Dict) -> None:
        safe_meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                     for k, v in metadata.items()}
        self.collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[safe_meta]
        )

    def query(self, embedding: List[float], top_k: int = 5) -> List[Tuple[str, float, Dict]]:
        count = self.collection.count()
        if count == 0:
            return []
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, count)
        )
        if not results["ids"][0]:
            return []
        return list(zip(
            results["ids"][0],
            results["distances"][0],
            results["metadatas"][0]
        ))

    def delete(self, doc_id: str) -> None:
        self.collection.delete(ids=[doc_id])

    def count(self) -> int:
        return self.collection.count()
