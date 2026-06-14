"""Command-line ingestion pipeline for the local RAG knowledge base."""
from __future__ import annotations

import argparse
from typing import Any, Dict

from settings import RAG_CONFIG

from .document_loader import iter_chunks, load_text_documents
from .retriever import KnowledgeRetriever


def ingest_documents(
    documents_dir: str,
    knowledge_base_path: str,
    collection_name: str,
    rebuild: bool = False,
    max_chars: int = 600,
    overlap: int = 100,
) -> Dict[str, Any]:
    documents = load_text_documents(documents_dir)
    chunks = list(iter_chunks(documents, max_chars=max_chars, overlap=overlap))

    retriever = KnowledgeRetriever(
        knowledge_base_path=knowledge_base_path,
        collection_name=collection_name,
        top_k=RAG_CONFIG.get("top_k", 3),
    )
    if not retriever.initialized:
        return {"status": "error", "message": retriever.error or "RAG retriever not initialized"}

    try:
        if rebuild:
            retriever.rebuild()
        result = retriever.add_documents(chunks)  # type: ignore[arg-type]
        return {
            **result,
            "documents_loaded": len(documents),
            "chunks_loaded": len(chunks),
            "documents_dir": documents_dir,
            "knowledge_base_path": knowledge_base_path,
            "collection_name": collection_name,
        }
    finally:
        retriever.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or update the Aligo RAG knowledge base.")
    parser.add_argument("--documents-dir", default=RAG_CONFIG.get("documents_dir", "data/documents"))
    parser.add_argument("--knowledge-base-path", default=RAG_CONFIG.get("knowledge_base_path", "data/rag_knowledge"))
    parser.add_argument("--collection", default=RAG_CONFIG.get("collection_name", "business_travel_knowledge"))
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    result = ingest_documents(
        documents_dir=args.documents_dir,
        knowledge_base_path=args.knowledge_base_path,
        collection_name=args.collection,
        rebuild=args.rebuild,
    )
    print(result)


if __name__ == "__main__":
    main()

