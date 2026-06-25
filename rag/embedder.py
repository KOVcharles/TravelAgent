"""Embedding interfaces for RAG vector stores."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class TextEmbedder(ABC):
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

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self.model.encode(text).tolist() for text in texts]

    def embed_query(self, query: str) -> List[float]:
        return self.model.encode(query).tolist()


# TODO: Add multimodal embedders behind TextEmbedder or a sibling interface
# when image/table embeddings become part of the production dependency set.
