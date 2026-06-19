"""
Factory: returns the configured vector store backend.
Switch via VECTOR_BACKEND env var: "chroma" (default) or "pinecone".
"""
import os
from .base import VectorStoreBase
from .chroma_store import ChromaStore


def get_vector_store(collection: str = "paraiq", backend: str = None) -> VectorStoreBase:
    backend = backend or os.getenv("VECTOR_BACKEND", "chroma")

    if backend == "chroma":
        return ChromaStore(
            collection_name=collection,
            persist_dir=os.getenv("CHROMA_PERSIST_DIR", "/root/nlp-portfolio/chroma_db")
        )

    elif backend == "pinecone":
        from .pinecone_store import PineconeStore
        return PineconeStore(
            api_key=os.getenv("PINECONE_API_KEY"),
            index_name=os.getenv("PINECONE_INDEX", "paraiq"),
            dimension=int(os.getenv("PINECONE_DIMENSION", "384"))
        )

    raise ValueError(f"Unknown VECTOR_BACKEND: '{backend}'. Use 'chroma' or 'pinecone'.")
