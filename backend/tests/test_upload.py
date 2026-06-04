"""
Tests for the /upload HTTP endpoint and its validation rules.

Scope:
  - 415 unsupported file type
  - 413 file too large
  - 400 empty file / missing filename
  - 200 happy paths for text/plain and text/markdown
  - In-memory store is populated after a successful upload
  - document_id surfaces in the response when the Supabase path activates
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.embeddings import _MEMORY_STORE, get_memory_store
from app.services.pipeline import DEMO_USER_ID
from main import app

client = TestClient(app)


# ── Validation ────────────────────────────────────────────────────────────────

def test_upload_rejects_unsupported_type():
    r = client.post(
        "/upload",
        files={"file": (
            "resume.docx", b"fake docx bytes",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )},
    )
    assert r.status_code == 415
    assert "Unsupported file type" in r.json()["detail"]


def test_upload_rejects_empty_file():
    r = client.post(
        "/upload",
        files={"file": ("resume.txt", b"", "text/plain")},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_upload_rejects_oversized_file():
    huge = b"x" * (11 * 1024 * 1024)  # 11MB > 10MB limit
    r = client.post(
        "/upload",
        files={"file": ("resume.txt", huge, "text/plain")},
    )
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


def test_upload_accepts_markdown():
    md_resume = b"# Min\n\nUCLA CS, building Personify."
    r = client.post(
        "/upload",
        files={"file": ("resume.md", md_resume, "text/markdown")},
    )
    assert r.status_code == 200
    assert r.json()["chunks_stored"] >= 1


# ── Memory store integration ──────────────────────────────────────────────────

def test_memory_store_is_populated_after_upload():
    """Uploading a text file should populate the in-memory chunk store."""
    _MEMORY_STORE.clear()

    sample_resume = (
        "Min Phone Myat Zaw — UCLA Computer Science, expected 2027.\n\n"
        "Experience: built a Chrome extension that uses a LangChain pipeline "
        "to fill personal statement questions on job applications.\n\n"
        "Skills: Python, JavaScript, FastAPI, React, LangChain, RAG."
    ).encode("utf-8")

    r = client.post(
        "/upload",
        files={"file": ("resume.txt", sample_resume, "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["chunks_stored"] >= 1
    # Demo user is not a UUID and Supabase isn't configured in tests,
    # so we expect the in-memory fallback path.
    assert body["stored_in"] == "memory"
    assert body.get("document_id") is None  # no docs-table row for demo-user

    store = get_memory_store()
    assert DEMO_USER_ID in store
    assert len(store[DEMO_USER_ID]) >= 1


# ── document_id wiring (the new Supabase-aware path) ──────────────────────────

class TestDocumentIdWiring:
    """
    Verify that ingest_document only attempts the Supabase documents-table
    insert when (a) Supabase is configured AND (b) user_id looks like a
    UUID. With either condition unmet, the behavior is exactly today's.
    """

    @patch("app.services.embeddings._supabase_configured", return_value=False)
    def test_no_supabase_means_memory(self, _cfg):
        from app.services.embeddings import ingest_document
        _MEMORY_STORE.clear()
        summary = ingest_document(
            file_bytes=b"hello world this is a resume",
            content_type="text/plain",
            filename="resume.txt",
            user_id="demo-user",
        )
        assert summary["stored_in"] == "memory"
        assert "document_id" not in summary

    @patch("app.services.embeddings._insert_documents_row", return_value=True)
    @patch("app.services.embeddings.save_chunks_pgvector", create=True)
    @patch("app.services.embeddings._supabase_configured", return_value=True)
    def test_supabase_with_uuid_user_inserts_documents_row(
        self, _cfg, mock_save, mock_insert,
    ):
        """
        If user_id is a UUID and Supabase is configured, we should:
          1. insert a documents row
          2. call save_chunks_pgvector with the new document_id
          3. report stored_in='supabase'
        """
        from app.services.embeddings import ingest_document
        # The save_chunks_pgvector reference is created at call time inside
        # ingest_document via a lazy import; patch on the source module so
        # the lazy import resolves to our mock.
        with patch("app.services.retrieval.save_chunks_pgvector") as mock_retrieval_save:
            summary = ingest_document(
                file_bytes=b"hello world resume content here",
                content_type="text/plain",
                filename="resume.txt",
                user_id="11111111-2222-3333-4444-555555555555",
            )
            assert summary["stored_in"] == "supabase"
            assert summary.get("document_id") is not None
            # save_chunks_pgvector must receive the same document_id that
            # _insert_documents_row was called with.
            assert mock_insert.called
            insert_doc_id = mock_insert.call_args.args[3]
            assert mock_retrieval_save.called
            assert mock_retrieval_save.call_args.kwargs["document_id"] == insert_doc_id

    @patch("app.services.embeddings._supabase_configured", return_value=True)
    def test_supabase_with_non_uuid_user_skips_documents_row(self, _cfg):
        """
        Demo-user is not a UUID — even if Supabase is configured, we must
        NOT attempt the documents-table insert (the FK would fail). We
        should still try save_chunks_pgvector with document_id=None.
        """
        from app.services.embeddings import ingest_document
        with patch("app.services.retrieval.save_chunks_pgvector") as mock_save, \
             patch("app.services.embeddings._insert_documents_row") as mock_insert:
            summary = ingest_document(
                file_bytes=b"hello world",
                content_type="text/plain",
                filename="r.txt",
                user_id="demo-user",
            )
            # documents-table insert should never be attempted
            mock_insert.assert_not_called()
            # chunks should still be persisted
            mock_save.assert_called_once()
            assert mock_save.call_args.kwargs["document_id"] is None
            assert summary["stored_in"] == "pgvector"
            assert "document_id" not in summary
