"""Data structures shared by the RAG ingestion and retrieval pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RawDocument:
    content: bytes
    source_path: str
    filename: str
    file_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    source_path: str
    filename: str
    file_type: str
    page_number: Optional[int] = None
    content_type: str = "text"
    title: str = ""
    category: str = "business_travel"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentChunk:
    content: str
    source_path: str
    filename: str
    file_type: str
    page_number: Optional[int]
    chunk_index: int
    content_type: str
    hash: str
    title: str = ""
    category: str = "business_travel"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, Any]:
        data = dict(self.metadata)
        data.update(
            {
                "source_path": self.source_path,
                "filename": self.filename,
                "file_type": self.file_type,
                "page_number": self.page_number,
                "chunk_index": self.chunk_index,
                "content_type": self.content_type,
                "hash": self.hash,
                "title": self.title,
                "category": self.category,
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


@dataclass(frozen=True)
class IngestionReport:
    status: str
    source_path: str
    documents_loaded: int = 0
    pages_parsed: int = 0
    chunks_loaded: int = 0
    added_count: int = 0
    total_count: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "source_path": self.source_path,
            "documents_loaded": self.documents_loaded,
            "pages_parsed": self.pages_parsed,
            "chunks_loaded": self.chunks_loaded,
            "added_count": self.added_count,
            "total_count": self.total_count,
            "errors": self.errors,
            **self.metadata,
        }


@dataclass(frozen=True)
class SourceDocument:
    """Backward-compatible text document shape used by older callers."""

    content: str
    source_path: str
    title: str
    category: str = "business_travel"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return Path(self.source_path).name

    @property
    def file_type(self) -> str:
        return Path(self.source_path).suffix.lstrip(".").lower() or "txt"


@dataclass(frozen=True, init=False)
class KnowledgeChunk(DocumentChunk):
    """Backward-compatible chunk constructor for older callers."""

    def __init__(
        self,
        content: str,
        source_path: str,
        title: str,
        category: str,
        chunk_index: int,
        metadata: Optional[Dict[str, Any]] = None,
        filename: Optional[str] = None,
        file_type: Optional[str] = None,
        page_number: Optional[int] = None,
        content_type: str = "text",
        hash: Optional[str] = None,
    ):
        import hashlib

        resolved_filename = filename or Path(source_path).name
        resolved_file_type = file_type or Path(resolved_filename).suffix.lstrip(".").lower() or "txt"
        resolved_hash = hash or hashlib.sha256(
            f"{source_path}:{page_number}:{chunk_index}:{content}".encode("utf-8")
        ).hexdigest()
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "source_path", source_path)
        object.__setattr__(self, "filename", resolved_filename)
        object.__setattr__(self, "file_type", resolved_file_type)
        object.__setattr__(self, "page_number", page_number)
        object.__setattr__(self, "chunk_index", chunk_index)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "hash", resolved_hash)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "metadata", metadata or {})

