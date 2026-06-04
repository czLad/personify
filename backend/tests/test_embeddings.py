"""
Unit tests for the embeddings service.

These are pure-function tests that don't require a Gemini key:
  - extract_text (PDF + plain text + pdf fallback to raw decode)
  - chunk_text (basic chunking, empty input, short input)
  - _looks_like_uuid (the new helper that gates the Supabase docs-table path)

LLM-backed paths (embed_texts, embed_query, full ingest_document)
have integration coverage in test_upload.py — we don't re-test the
embedding call here.
"""
from __future__ import annotations

from app.services.embeddings import (
    _looks_like_uuid,
    chunk_text,
    extract_text,
)

# ── extract_text ──────────────────────────────────────────────────────────────

class TestExtractText:
    def test_plain_text_utf8(self):
        text = "Hello, my résumé says I love Python.".encode("utf-8")
        assert extract_text(text, "text/plain", "resume.txt").startswith("Hello")

    def test_plain_text_strips_whitespace(self):
        text = b"\n\n  trimmed me  \n\n"
        assert extract_text(text, "text/plain", "x.txt") == "trimmed me"

    def test_pdf_extension_triggers_pdf_path(self):
        # Garbage bytes — PDF parse will fail, falls back to raw decode.
        # The fallback should still yield SOMETHING rather than crash.
        result = extract_text(b"not a real pdf", "application/pdf", "fake.pdf")
        assert isinstance(result, str)

    def test_empty_bytes_returns_empty(self):
        assert extract_text(b"", "text/plain", "x.txt") == ""

    def test_non_utf8_bytes_are_lossy_decoded(self):
        # Invalid utf-8; errors="ignore" means we get a (possibly shorter) str back.
        text = b"\xff\xfeABC"
        result = extract_text(text, "text/plain", "x.txt")
        assert "ABC" in result


# ── chunk_text ────────────────────────────────────────────────────────────────

class TestChunkText:
    def test_empty_returns_empty_list(self):
        assert chunk_text("") == []

    def test_short_input_returns_one_chunk(self):
        chunks = chunk_text("Just a short resume blurb.")
        assert len(chunks) == 1
        assert chunks[0] == "Just a short resume blurb."

    def test_long_input_yields_multiple_chunks(self):
        # 2500-char input with chunk_size=800 should produce >= 3 chunks.
        long_text = ("Paragraph about Python and machine learning. " * 60)
        chunks = chunk_text(long_text, chunk_size=800, chunk_overlap=100)
        assert len(chunks) >= 3
        # Chunks shouldn't be massively larger than the requested size.
        assert all(len(c) <= 900 for c in chunks)

    def test_custom_chunk_size_respected(self):
        text = "x" * 300
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
        assert len(chunks) >= 3


# ── _looks_like_uuid (gates the Supabase docs-table path) ─────────────────────

class TestLooksLikeUuid:
    def test_real_uuid_is_recognized(self):
        assert _looks_like_uuid("11111111-2222-3333-4444-555555555555") is True

    def test_demo_user_string_is_not_uuid(self):
        assert _looks_like_uuid("demo-user") is False

    def test_empty_string_is_not_uuid(self):
        assert _looks_like_uuid("") is False

    def test_almost_uuid_missing_dashes(self):
        # uuid.UUID() is lenient: accepts no-dash hex. That's fine — we
        # mostly care that demo-user and similar non-UUID strings are
        # rejected, which they are.
        assert _looks_like_uuid("111111112222333344445555555555ff") is True
