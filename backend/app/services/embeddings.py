"""
Embeddings service.

Handles two responsibilities:
  1. Extract raw text from an uploaded document (PDF or plain text).
  2. Chunk that text and embed each chunk using Gemini's text-embedding model.

Embeddings are stored in two places depending on what is available:
  - Supabase pgvector (production path) — handled by app.services.retrieval
  - In-memory dict (fallback for demo when Supabase isn't wired up yet)

This dual path means the demo never breaks because Dev's pgvector setup
isn't ready. The MLE work isn't blocked on infrastructure.
"""
from __future__ import annotations

import io
import logging
from typing import Iterable

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── In-memory fallback store ──────────────────────────────────────────────────
# Keyed by user_id → list of (chunk_text, embedding) tuples.
# This exists so the autofill pipeline can still demo even if Supabase
# pgvector isn't set up. It is wiped on every server restart.
_MEMORY_STORE: dict[str, list[tuple[str, list[float]]]] = {}


# ── Document text extraction ──────────────────────────────────────────────────

def extract_text(file_bytes: bytes, content_type: str | None, filename: str = "") -> str:
    """
    Extract plain text from an uploaded document.

    Supports PDFs (via PyPDF2) and plain text. DOCX support can be added later
    by a teammate — for the MVP demo, PDF is enough.
    """
    is_pdf = (
        (content_type and "pdf" in content_type.lower())
        or filename.lower().endswith(".pdf")
    )

    if is_pdf:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages).strip()
        except Exception as e:
            logger.warning("PDF extraction failed: %s — falling back to raw decode", e)

    # Plain text fallback
    try:
        return file_bytes.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[str]:
    """
    Split a document into overlapping chunks suitable for embedding.

    800 chars (~200 tokens) with 100-char overlap is a sensible default for
    resumes and short essays. If a document is shorter than chunk_size, this
    returns a single chunk.
    """
    if not text:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [c for c in splitter.split_text(text) if c.strip()]


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """
    Embed a batch of texts using Gemini's text-embedding-004 model.

    Returns one 768-dim vector per input. If the Gemini API key is missing,
    returns deterministic zero-vectors so the rest of the pipeline still runs
    in a "broken-but-doesn't-crash" mode useful for local development.
    """
    text_list = list(texts)
    if not text_list:
        return []

    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY missing — returning zero vectors")
        return [[0.0] * 768 for _ in text_list]

    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)

    vectors: list[list[float]] = []
    for text in text_list:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
        )
        vectors.append(result["embedding"])
    return vectors


def embed_query(text: str) -> list[float]:
    """Embed a single query string. Uses retrieval_query task type for best results."""
    if not settings.gemini_api_key:
        return [0.0] * 768

    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_query",
    )
    return result["embedding"]


# ── Ingestion (the function called from /upload) ──────────────────────────────

def ingest_document(file_bytes: bytes, content_type: str | None, filename: str, user_id: str) -> dict:
    """
    End-to-end ingestion: extract → chunk → embed → store.

    Stores in pgvector if Supabase is configured, otherwise stores in the
    in-memory fallback. Returns a summary suitable for the /upload response.
    """
    text = extract_text(file_bytes, content_type, filename)
    if not text:
        return {"status": "no_text_extracted", "chunks_stored": 0}

    chunks = chunk_text(text)
    embeddings = embed_texts(chunks)

    # Try to persist in pgvector; fall back to memory.
    stored_in = "memory"
    try:
        from app.services.retrieval import save_chunks_pgvector
        save_chunks_pgvector(user_id=user_id, chunks=chunks, embeddings=embeddings)
        stored_in = "pgvector"
    except Exception as e:
        logger.info("pgvector save failed (%s) — using in-memory fallback", e)
        _MEMORY_STORE.setdefault(user_id, []).clear()
        _MEMORY_STORE[user_id].extend(zip(chunks, embeddings))

    return {
        "status": "ok",
        "chunks_stored": len(chunks),
        "stored_in": stored_in,
        "preview": chunks[0][:200] if chunks else "",
    }


def get_memory_store() -> dict[str, list[tuple[str, list[float]]]]:
    """Exposed so retrieval.py can read the fallback store."""
    return _MEMORY_STORE