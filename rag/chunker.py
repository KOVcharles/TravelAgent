"""Text chunking utilities for RAG ingestion."""
from __future__ import annotations

import hashlib
import re
from typing import List

from .schemas import DocumentChunk, ParsedDocument, SourceDocument


_QUESTION_HEADING_RE = re.compile(r"^Q\d+\s*[:：]", re.IGNORECASE)
_SECTION_HEADING_RE = re.compile(r"^[一二三四五六七八九十]+[、.．]\s*\S+")
_NUMBERED_HEADING_RE = re.compile(r"^\d+[.．]\s+\S+")


class TextChunker:
    def __init__(self, max_chars: int = 600, overlap: int = 100):
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, documents: List[ParsedDocument]) -> List[DocumentChunk]:
        chunks: List[DocumentChunk] = []
        chunk_index = 1
        for document in documents:
            for content in split_text(document.text, max_chars=self.max_chars, overlap=self.overlap):
                chunk_hash = _hash_chunk(document.source_path, document.page_number, chunk_index, content)
                metadata = dict(document.metadata)
                metadata.setdefault("parent_doc", document.filename)
                chunks.append(
                    DocumentChunk(
                        content=content,
                        source_path=document.source_path,
                        filename=document.filename,
                        file_type=document.file_type,
                        page_number=document.page_number,
                        chunk_index=chunk_index,
                        content_type=document.content_type,
                        hash=chunk_hash,
                        title=document.title,
                        category=document.category,
                        metadata=metadata,
                    )
                )
                chunk_index += 1
        return chunks


def split_text(text: str, max_chars: int = 600, overlap: int = 100) -> List[str]:
    """Split text into topic-aware chunks with an overlap fallback for long blocks."""
    if not text.strip():
        return []

    paragraphs = _paragraphs(text)
    chunks: List[str] = []
    current_chunk = ""
    for paragraph in paragraphs:
        if not paragraph:
            continue

        starts_topic = _starts_new_topic(paragraph)
        if current_chunk and starts_topic:
            chunks.extend(_split_long_text(current_chunk, max_chars, overlap))
            current_chunk = ""

        if current_chunk and len(current_chunk) + len(paragraph) + 2 > max_chars:
            chunks.extend(_split_long_text(current_chunk, max_chars, overlap))
            current_chunk = ""

        if len(paragraph) > max_chars:
            if current_chunk:
                chunks.extend(_split_long_text(current_chunk, max_chars, overlap))
                current_chunk = ""
            chunks.extend(_split_long_text(paragraph, max_chars, overlap))
            continue

        current_chunk = f"{current_chunk}\n\n{paragraph}".strip()

    if current_chunk:
        chunks.extend(_split_long_text(current_chunk, max_chars, overlap))
    return chunks


def chunk_document(document: SourceDocument, max_chars: int = 600, overlap: int = 100) -> List[DocumentChunk]:
    parsed = ParsedDocument(
        text=document.content,
        source_path=document.source_path,
        filename=document.filename,
        file_type=document.file_type,
        page_number=document.metadata.get("page_number"),
        title=document.title,
        category=document.category,
        metadata=document.metadata,
    )
    return TextChunker(max_chars=max_chars, overlap=overlap).chunk([parsed])


def _paragraphs(text: str) -> List[str]:
    paragraphs: List[str] = []
    current: List[str] = []
    for line in text.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append("\n".join(current).strip())
            current = []
    if current:
        paragraphs.append("\n".join(current).strip())
    return paragraphs


def _starts_new_topic(paragraph: str) -> bool:
    first_line = paragraph.strip().splitlines()[0].strip()
    return bool(
        _QUESTION_HEADING_RE.match(first_line)
        or _SECTION_HEADING_RE.match(first_line)
        or _NUMBERED_HEADING_RE.match(first_line)
    )


def _split_long_text(text: str, max_chars: int, overlap: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    start = 0
    step_back = min(max(overlap, 0), max_chars - 1)
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - step_back)
    return chunks


def _hash_chunk(source_path: str, page_number: int | None, chunk_index: int, content: str) -> str:
    payload = f"{source_path}:{page_number}:{chunk_index}:{content}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
