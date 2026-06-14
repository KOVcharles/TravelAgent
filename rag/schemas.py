"""Small data structures shared by the RAG pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class SourceDocument:
    content: str
    source_path: str
    title: str
    category: str = "business_travel"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeChunk:
    content: str
    source_path: str
    title: str
    category: str
    chunk_index: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, Any]:
        data = dict(self.metadata)
        data.update(
            {
                "source_path": self.source_path,
                "title": self.title,
                "category": self.category,
                "chunk_index": self.chunk_index,
            }
        )
        return data


@dataclass(frozen=True)
class RetrievalResult:
    id: Any
    content: str
    metadata: Dict[str, Any]
    distance: Optional[float] = None
    vector_rank: Optional[int] = None
    bm25_rank: Optional[int] = None
    bm25_score: Optional[float] = None
    fusion_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "distance": self.distance,
            "vector_rank": self.vector_rank,
            "bm25_rank": self.bm25_rank,
            "bm25_score": self.bm25_score,
            "fusion_score": self.fusion_score,
        }

