"""Embedding interfaces for RAG vector stores."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List

import requests


class TextEmbedder(ABC):
    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        raise NotImplementedError


class SentenceTransformerEmbedder(TextEmbedder):
    def __init__(self, model_name_or_path: str):
        from .milvus_store import _get_embedding_model, resolve_embedding_model

        self.model = _get_embedding_model(resolve_embedding_model(model_name_or_path))

    def dimension(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self.model.encode(text).tolist() for text in texts]

    def embed_query(self, query: str) -> List[float]:
        return self.model.encode(query).tolist()


class SiliconFlowEmbedder(TextEmbedder):
    """OpenAI-compatible SiliconFlow embeddings client."""

    def __init__(
        self,
        api_key: str,
        model: str = "BAAI/bge-m3",
        base_url: str = "https://api.siliconflow.cn/v1",
        dimension: int = 1024,
        timeout_sec: float = 30.0,
        batch_size: int = 32,
        session: Any | None = None,
    ):
        if not api_key:
            raise RuntimeError("SiliconFlow embedding API key is missing")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._dimension = int(dimension)
        self.timeout_sec = float(timeout_sec)
        self.batch_size = max(1, int(batch_size))
        self.session = session or requests.Session()

    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        embeddings: List[List[float]] = []
        for start in range(0, len(texts), self.batch_size):
            embeddings.extend(self._request_embeddings(texts[start : start + self.batch_size]))
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        embeddings = self.embed_texts([query])
        return embeddings[0] if embeddings else []

    def _request_embeddings(self, texts: List[str]) -> List[List[float]]:
        response = self.session.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": texts,
                "encoding_format": "float",
            },
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        embeddings = [item.get("embedding", []) for item in data]
        if len(embeddings) != len(texts):
            raise RuntimeError("SiliconFlow embedding response count mismatch")
        for embedding in embeddings:
            if len(embedding) != self._dimension:
                raise RuntimeError(
                    f"SiliconFlow embedding dimension mismatch: expected {self._dimension}, got {len(embedding)}"
                )
        return embeddings


def create_text_embedder(
    backend: str,
    model: str,
    api_key: str | None = None,
    base_url: str = "https://api.siliconflow.cn/v1",
    dimension: int = 1024,
    timeout_sec: float = 30.0,
    batch_size: int = 32,
) -> TextEmbedder:
    normalized = (backend or "siliconflow").lower()
    if normalized == "local":
        return SentenceTransformerEmbedder(model)
    if normalized == "siliconflow":
        return SiliconFlowEmbedder(
            api_key=api_key or "",
            model=model,
            base_url=base_url,
            dimension=dimension,
            timeout_sec=timeout_sec,
            batch_size=batch_size,
        )
    raise ValueError(f"Unsupported RAG embedding backend: {backend}")


# TODO: Add multimodal embedders behind TextEmbedder or a sibling interface
# when image/table embeddings become part of the production dependency set.
