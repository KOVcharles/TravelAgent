"""Document loading interfaces and filesystem implementation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, List

from .schemas import RawDocument


class DocumentLoader(ABC):
    @abstractmethod
    def load(self, path: str | Path) -> List[RawDocument]:
        raise NotImplementedError


class FileSystemDocumentLoader(DocumentLoader):
    def __init__(self, supported_file_types: Iterable[str] = ("txt", "pdf")):
        self.supported_file_types = {item.lower().lstrip(".") for item in supported_file_types}

    def load(self, path: str | Path) -> List[RawDocument]:
        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(f"Document path does not exist: {root}")

        if root.is_file():
            return [self._load_file(root)]

        documents: List[RawDocument] = []
        for file_path in sorted(item for item in root.rglob("*") if item.is_file()):
            file_type = file_path.suffix.lower().lstrip(".")
            if file_type not in self.supported_file_types:
                continue
            documents.append(self._load_file(file_path))
        return documents

    def _load_file(self, path: Path) -> RawDocument:
        file_type = path.suffix.lower().lstrip(".")
        return RawDocument(
            content=path.read_bytes(),
            source_path=str(path),
            filename=path.name,
            file_type=file_type,
            metadata={"source": "business_travel_documents", "parent_doc": path.name},
        )
