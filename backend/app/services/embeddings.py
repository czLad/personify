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

Note on inline imports: heavy libs (google.generativeai, PyPDF2, supabase)
are imported inside functions, not at the top. This keeps module load fast
for tests that don't need them, and avoids a circular import with retrieval.py.
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

# Tracks whether genai.configure() has been called this process. Lazy + one-shot
# so we don't reconfigure on every embed call.
_gemini_configured = False


# ── Constants ─────────────────────────────────────────────────────────────────

EMBEDDING_DIM = 768
EMBEDDING_BATCH_SIZE = 100  # Gemini accepts batched inputs in a single call


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
            # Lazy: only load PyPDF2 if the file is actually a PDF.
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

def _configure_gemini_once() -> bool:
    """
    Configure the Gemini client lazily and at most once per process.
    Returns True if the client is ready, False if no API key is set
    (in which case callers should use the zero-vector fallback).
    """
    global _gemini_configured
    if not settings.gemini_api_key:
        return False
    if not _gemini_configured:
        # Lazy: google.generativeai is slow to import (gRPC, protobuf, etc).
        # Only load it when we actually have a key to use.
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        _gemini_configured = True
    return True


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """
    Embed a batch of texts using Gemini's gemini-embedding-001 model.

    Returns one EMBEDDING_DIM-dim vector per input. If the Gemini API key is
    missing, returns deterministic zero-vectors so the rest of the pipeline
    still runs in a "broken-but-doesn't-crash" mode useful for local dev.

    Batches requests to Gemini in groups of EMBEDDING_BATCH_SIZE to cut HTTP
    round-trips. For a typical resume (5-15 chunks) this is a single call.
    """
    text_list = list(texts)
    if not text_list:
        return []

    if not _configure_gemini_once():
        logger.warning("GEMINI_API_KEY missing — returning zero vectors")
        return [[0.0] * EMBEDDING_DIM for _ in text_list]

    # Lazy: same reason as in _configure_gemini_once. Already cached after first call.
    import google.generativeai as genai

    vectors: list[list[float]] = []
    for i in range(0, len(text_list), EMBEDDING_BATCH_SIZE):
        batch = text_list[i : i + EMBEDDING_BATCH_SIZE]
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=batch,
            task_type="retrieval_document",
            output_dimensionality=EMBEDDING_DIM,
        )
        vectors.extend(result["embedding"])
    return vectors


def embed_query(text: str) -> list[float]:
    """
    Embed a single query string. Uses retrieval_query task type for best results.
    Returns EMBEDDING_DIM dims to match the document embeddings stored above.
    """
    if not _configure_gemini_once():
        return [0.0] * EMBEDDING_DIM

    # Lazy: same reason. Cached after first call.
    import google.generativeai as genai
    result = genai.embed_content(
        model="models/gemini-embedding-001",
        content=text,
        task_type="retrieval_query",
        output_dimensionality=EMBEDDING_DIM,
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
        # Lazy: avoids a circular import. retrieval.py imports from this file too.
        from app.services.retrieval import save_chunks_pgvector
        save_chunks_pgvector(user_id=user_id, chunks=chunks, embeddings=embeddings)
        stored_in = "pgvector"
    except Exception as e:
        logger.info("pgvector save failed (%s) — using in-memory fallback", e)
        _MEMORY_STORE.setdefault(user_id, []).clear()
        _MEMORY_STORE[user_id].extend(zip(chunks, embeddings))

    # ─────────────────────────────────────────────────────────────────────────
    # FUTURE (Dev's path): once auth provides real UUIDs and Supabase is wired,
    # uncomment to also persist a `documents` table row and link chunks to it.
    # This is the production path; the block above is the demo path.
    #
    # Requires:
    #   - settings.supabase_url and settings.supabase_service_key set in .env
    #   - user_id is a real auth.users UUID (not "demo-user")
    #   - migrations 0001_initial.sql and 0002_match_chunks_rpc.sql applied
    #
    # import uuid
    # from supabase import create_client  # lazy: only load if Supabase is configured
    #
    # if settings.supabase_url and settings.supabase_service_key:
    #     try:
    #         supabase = create_client(settings.supabase_url, settings.supabase_service_key)
    #         document_id = str(uuid.uuid4())
    #         storage_path = f"uploads/{user_id}/{filename}"
    #
    #         supabase.table("documents").insert({
    #             "id": document_id,
    #             "user_id": user_id,
    #             "filename": filename,
    #             "content_type": content_type,
    #             "storage_path": storage_path,
    #         }).execute()
    #
    #         # Re-insert chunks with the document_id so they link back to the file.
    #         # save_chunks_pgvector above wrote chunks without a document_id;
    #         # to use this block, refactor save_chunks_pgvector to accept document_id
    #         # or call supabase.table("document_chunks").update(...) here.
    #         logger.info("Stored document %s with %d chunks for user %s",
    #                     document_id, len(chunks), user_id)
    #
    #         return {
    #             "status": "ok",
    #             "chunks_stored": len(chunks),
    #             "stored_in": "supabase",
    #             "document_id": document_id,
    #             "preview": chunks[0][:200] if chunks else "",
    #         }
    #     except Exception as e:
    #         logger.warning("Supabase document insert failed: %s", e)
    # ─────────────────────────────────────────────────────────────────────────

    return {
        "status": "ok",
        "chunks_stored": len(chunks),
        "stored_in": stored_in,
        "preview": chunks[0][:200] if chunks else "",
    }


def get_memory_store() -> dict[str, list[tuple[str, list[float]]]]:
    """Exposed so retrieval.py can read the fallback store."""
    return _MEMORY_STORE