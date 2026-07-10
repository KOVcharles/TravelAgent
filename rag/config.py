"""Configuration object for the RAG pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Tuple

from settings import RAG_CONFIG


@dataclass(frozen=True)
class RAGPipelineConfig:
    embedding_backend: str = "siliconflow"
    embedding_model: str = "BAAI/bge-m3"
    embedding_api_key: str | None = None
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_dimension: int = 1024
    embedding_batch_size: int = 32
    embedding_timeout_sec: float = 30.0
    documents_dir: str = "data/documents"
    knowledge_base_path: str = "data/rag_knowledge"
    collection_name: str = "business_travel_knowledge"
    chunk_size: int = 600
    chunk_overlap: int = 100
    top_k: int = 3
    vector_top_k: int = 10
    bm25_top_k: int = 10
    supported_file_types: Tuple[str, ...] = field(default_factory=lambda: ("txt", "md", "pdf"))

    @classmethod
    def from_settings(cls, overrides: Optional[Dict[str, Any]] = None) -> "RAGPipelineConfig":
        data = {
            "embedding_backend": RAG_CONFIG.get("embedding_backend", cls.embedding_backend),
            "embedding_model": RAG_CONFIG.get("embedding_model", cls.embedding_model),
            "embedding_api_key": RAG_CONFIG.get("embedding_api_key", cls.embedding_api_key),
            "embedding_base_url": RAG_CONFIG.get("embedding_base_url", cls.embedding_base_url),
            "embedding_dimension": RAG_CONFIG.get("embedding_dimension", cls.embedding_dimension),
            "embedding_batch_size": RAG_CONFIG.get("embedding_batch_size", cls.embedding_batch_size),
            "embedding_timeout_sec": RAG_CONFIG.get("embedding_timeout_sec", cls.embedding_timeout_sec),
            "documents_dir": RAG_CONFIG.get("documents_dir", cls.documents_dir),
            "knowledge_base_path": RAG_CONFIG.get("knowledge_base_path", cls.knowledge_base_path),
            "collection_name": RAG_CONFIG.get("collection_name", cls.collection_name),
            "chunk_size": RAG_CONFIG.get("chunk_size", cls.chunk_size),
            "chunk_overlap": RAG_CONFIG.get("chunk_overlap", cls.chunk_overlap),
            "top_k": RAG_CONFIG.get("top_k", cls.top_k),
            "vector_top_k": RAG_CONFIG.get("vector_top_k", cls.vector_top_k),
            "bm25_top_k": RAG_CONFIG.get("bm25_top_k", cls.bm25_top_k),
        }
        if overrides:
            data.update({key: value for key, value in overrides.items() if value is not None})
        if "supported_file_types" in data:
            data["supported_file_types"] = _normalize_file_types(data["supported_file_types"])
        return cls(**data)


def _normalize_file_types(value: Iterable[str] | str) -> Tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip().lstrip(".").lower() for item in value.split(",") if item.strip())
    return tuple(str(item).strip().lstrip(".").lower() for item in value if str(item).strip())
