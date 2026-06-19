"""
Pinecone serverless backend for ParaIQ vector store.
Activate with: VECTOR_BACKEND=pinecone in .env
Requires: PINECONE_API_KEY, PINECONE_INDEX (default: paraiq)
Dimension: 384 (all-MiniLM-L6-v2)
"""
from pinecone import Pinecone, ServerlessSpec
from typing import List, Tuple, Dict
from .base import VectorStoreBase


class PineconeStore(VectorStoreBase):

    def __init__(self, api_key: str, index_name: str, dimension: int = 384):
        pc = Pinecone(api_key=api_key)
        existing = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing:
            pc.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
        self.index = pc.Index(index_name)
        self._dimension = dimension

    def upsert(self, doc_id: str, embedding: List[float], metadata: Dict) -> None:
        safe_meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                     for k, v in metadata.items()}
        self.index.upsert(vectors=[{
            "id": doc_id,
            "values": embedding,
            "metadata": safe_meta
        }])

    def query(self, embedding: List[float], top_k: int = 5) -> List[Tuple[str, float, Dict]]:
        results = self.index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True
        )
        return [
            (m["id"], m["score"], m.get("metadata", {}))
            for m in results["matches"]
        ]

    def delete(self, doc_id: str) -> None:
        self.index.delete(ids=[doc_id])

    def count(self) -> int:
        stats = self.index.describe_index_stats()
        return stats.get("total_vector_count", 0)
