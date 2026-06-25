"""Content normalization interfaces for parsed RAG documents."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List

from .schemas import ParsedDocument


class DocumentNormalizer(ABC):
    @abstractmethod
    def normalize(self, documents: List[ParsedDocument]) -> List[ParsedDocument]:
        raise NotImplementedError


class TextNormalizer(DocumentNormalizer):
    def normalize(self, documents: List[ParsedDocument]) -> List[ParsedDocument]:
        normalized: List[ParsedDocument] = []
        for document in documents:
            text = _normalize_text(document.text)
            if not text:
                continue
            normalized.append(
                ParsedDocument(
                    text=text,
                    source_path=document.source_path,
                    filename=document.filename,
                    file_type=document.file_type,
                    page_number=document.page_number,
                    content_type=document.content_type,
                    title=document.title,
                    category=document.category,
                    metadata=document.metadata,
                )
            )
        return normalized


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    paragraphs = "\n".join(lines)
    paragraphs = re.sub(r"\n{3,}", "\n\n", paragraphs)
    return paragraphs.strip()
