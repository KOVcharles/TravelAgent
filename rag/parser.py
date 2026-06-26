"""Document parser interfaces and txt/pdf implementations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

from .document_loader import infer_category
from .schemas import ParsedDocument, RawDocument


class UnsupportedFileTypeError(ValueError):
    def __init__(self, file_type: str, source_path: str):
        super().__init__(f"Unsupported RAG document type '{file_type}' for file: {source_path}")
        self.file_type = file_type
        self.source_path = source_path


class DocumentParser(ABC):
    supported_file_types: tuple[str, ...] = ()

    @abstractmethod
    def parse(self, document: RawDocument) -> List[ParsedDocument]:
        raise NotImplementedError


class TxtParser(DocumentParser):
    supported_file_types = ("txt", "md")

    def parse(self, document: RawDocument) -> List[ParsedDocument]:
        text = document.content.decode("utf-8").strip()
        if not text:
            return []
        title = text.splitlines()[0].strip() if text.splitlines() else Path(document.filename).stem
        return [
            ParsedDocument(
                text=text,
                source_path=document.source_path,
                filename=document.filename,
                file_type=document.file_type,
                page_number=None,
                title=title,
                category=infer_category(Path(document.source_path)),
                metadata=dict(document.metadata),
            )
        ]


class PdfTextParser(DocumentParser):
    supported_file_types = ("pdf",)

    def parse(self, document: RawDocument) -> List[ParsedDocument]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF ingestion requires the optional 'pypdf' package.") from exc

        parsed: List[ParsedDocument] = []
        reader = PdfReader(document.source_path)
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception as exc:
                parsed.append(
                    ParsedDocument(
                        text="",
                        source_path=document.source_path,
                        filename=document.filename,
                        file_type=document.file_type,
                        page_number=index,
                        title=Path(document.filename).stem,
                        category=infer_category(Path(document.source_path)),
                        metadata={**document.metadata, "parse_error": str(exc)},
                    )
                )
                continue
            if not text:
                continue
            parsed.append(
                ParsedDocument(
                    text=text,
                    source_path=document.source_path,
                    filename=document.filename,
                    file_type=document.file_type,
                    page_number=index,
                    title=text.splitlines()[0].strip() if text.splitlines() else Path(document.filename).stem,
                    category=infer_category(Path(document.source_path)),
                    metadata=dict(document.metadata),
                )
            )
        return parsed


class ParserRegistry:
    def __init__(self, parsers: List[DocumentParser] | None = None):
        self.parsers: Dict[str, DocumentParser] = {}
        for parser in parsers or [TxtParser(), PdfTextParser()]:
            self.register(parser)

    def register(self, parser: DocumentParser) -> None:
        for file_type in parser.supported_file_types:
            self.parsers[file_type.lower()] = parser

    def parse(self, document: RawDocument) -> List[ParsedDocument]:
        parser = self.parsers.get(document.file_type.lower())
        if not parser:
            raise UnsupportedFileTypeError(document.file_type, document.source_path)
        return parser.parse(document)


# TODO: Add OCR, table extraction, image caption, and multimodal parsers behind
# this same DocumentParser interface when those dependencies are intentionally added.
