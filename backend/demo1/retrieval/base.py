"""
Abstract base class for ParaIQ vector store backends.
Both ChromaStore and PineconeStore implement this interface.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Dict

class VectorStoreBase(ABC):

    @abstractmethod
    def upsert(self, doc_id: str, embedding: List[float], metadata: Dict) -> None:
        """Insert or update a vector with associated metadata."""
        pass

    @abstractmethod
    def query(self, embedding: List[float], top_k: int = 5) -> List[Tuple[str, float, Dict]]:
        """Returns list of (doc_id, score, metadata), score is cosine distance 0-2."""
        pass

    @abstractmethod
    def delete(self, doc_id: str) -> None:
        """Remove a vector by ID."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Return total number of vectors stored."""
        pass
