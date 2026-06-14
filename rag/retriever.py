"""RAG retrieval facade used by agents and tests."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from settings import RAG_CONFIG

from .chunker import chunk_document
from .milvus_store import DEPENDENCIES_AVAILABLE, MilvusKnowledgeStore
from .schemas import KnowledgeChunk


class KnowledgeRetriever:
    def __init__(
        self,
        knowledge_base_path: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        top_k: int = 3,
    ):
        self.initialized = False
        self.store: Optional[MilvusKnowledgeStore] = None
        self.error: Optional[str] = None

        if not DEPENDENCIES_AVAILABLE:
            self.error = "RAG dependencies not installed"
            return

        try:
            self.store = MilvusKnowledgeStore(
                knowledge_base_path=knowledge_base_path or RAG_CONFIG.get("knowledge_base_path", "data/rag_knowledge"),
                collection_name=collection_name or RAG_CONFIG.get("collection_name", "business_travel_knowledge"),
                embedding_model=embedding_model or RAG_CONFIG.get("embedding_model", "data/models/bge-small-zh-v1.5"),
                top_k=top_k,
                vector_top_k=RAG_CONFIG.get("vector_top_k", 10),
                bm25_top_k=RAG_CONFIG.get("bm25_top_k", 10),
            )
            self.initialized = True
        except Exception as exc:
            self.error = str(exc)

    def add_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.store:
            return {"status": "error", "message": self.error or "RAG retriever not initialized"}

        chunks: List[KnowledgeChunk] = []
        for document in documents:
            if isinstance(document, KnowledgeChunk):
                chunks.append(document)
                continue
            content = document.get("content", "")
            metadata = document.get("metadata", {})
            chunks.append(
                KnowledgeChunk(
                    content=content,
                    source_path=metadata.get("source_path") or metadata.get("file_path") or "",
                    title=metadata.get("title") or "",
                    category=metadata.get("category") or "business_travel",
                    chunk_index=metadata.get("chunk_index") or len(chunks) + 1,
                    metadata=metadata,
                )
            )
        return self.store.add_chunks(chunks)

    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.store or not query:
            return []
        return self.store.hybrid_search(expand_query(query), top_k=top_k)

    def stats(self) -> Dict[str, Any]:
        if not self.store:
            return {"status": "error", "message": self.error or "RAG retriever not initialized"}
        return self.store.stats()

    def rebuild(self) -> None:
        if not self.store:
            raise RuntimeError(self.error or "RAG retriever not initialized")
        self.store.rebuild_collection()

    def close(self) -> None:
        if self.store:
            self.store.close()


def expand_query(query: str) -> str:
    """Add a few domain synonyms without introducing a query-rewrite LLM call."""
    text = query.strip()
    if any(word in text for word in ("餐补", "餐费", "餐饮", "饭补", "吃饭")):
        text = f"{text} 餐费 餐饮 早餐 午餐 晚餐 报销 个人零食 酒水"
    return text
