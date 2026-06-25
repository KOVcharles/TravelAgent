from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.config import RAGPipelineConfig
from rag.parser import UnsupportedFileTypeError
from rag.pipeline import RAGPipeline
from rag.vector_store import InMemoryVectorStore


def _pipeline(store=None):
    return RAGPipeline(
        config=RAGPipelineConfig(
            chunk_size=80,
            chunk_overlap=10,
            collection_name="test_collection",
            knowledge_base_path=":memory:",
        ),
        vector_store=store or InMemoryVectorStore(),
    )


def test_pipeline_ingests_txt_and_keeps_metadata(tmp_path: Path):
    doc = tmp_path / "01_travel_standards.txt"
    doc.write_text("Travel Standards\n\nBeijing hotel standard is 500.", encoding="utf-8")

    store = InMemoryVectorStore()
    report = _pipeline(store).ingest(doc)

    assert report.status == "success"
    assert report.documents_loaded == 1
    assert report.chunks_loaded == 1
    metadata = store.rows[0].to_metadata()
    assert metadata["source_path"] == str(doc)
    assert metadata["filename"] == "01_travel_standards.txt"
    assert metadata["file_type"] == "txt"
    assert metadata["page_number"] is None
    assert metadata["chunk_index"] == 1
    assert metadata["content_type"] == "text"
    assert metadata["hash"]


def test_pipeline_parses_pdf_by_page_and_keeps_page_number(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "policy.pdf"
    pdf.write_bytes(b"%PDF fake")

    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    fake_reader = SimpleNamespace(pages=[FakePage("Page one policy"), FakePage("Page two reimbursement")])
    monkeypatch.setitem(__import__("sys").modules, "pypdf", SimpleNamespace(PdfReader=lambda path: fake_reader))

    store = InMemoryVectorStore()
    report = _pipeline(store).ingest(pdf)

    assert report.status == "success"
    assert report.pages_parsed == 2
    assert [chunk.page_number for chunk in store.rows] == [1, 2]
    assert {chunk.file_type for chunk in store.rows} == {"pdf"}


def test_pipeline_rejects_unsupported_file_type(tmp_path: Path):
    doc = tmp_path / "image.png"
    doc.write_bytes(b"png")

    with pytest.raises(UnsupportedFileTypeError, match="Unsupported RAG document type"):
        _pipeline().ingest(doc)


def test_pipeline_handles_empty_txt_file(tmp_path: Path):
    doc = tmp_path / "empty.txt"
    doc.write_text("", encoding="utf-8")

    report = _pipeline().ingest(doc)

    assert report.status == "success"
    assert report.documents_loaded == 1
    assert report.pages_parsed == 0
    assert report.chunks_loaded == 0


def test_pipeline_query_returns_result_metadata(tmp_path: Path):
    doc = tmp_path / "faq.txt"
    doc.write_text("FAQ\n\nShanghai reimbursement needs invoice.", encoding="utf-8")
    pipeline = _pipeline()
    pipeline.ingest(doc)

    results = pipeline.query("invoice", top_k=1)

    assert len(results) == 1
    assert results[0].metadata["filename"] == "faq.txt"
    assert results[0].metadata["file_type"] == "txt"
    assert results[0].metadata["source_path"] == str(doc)
