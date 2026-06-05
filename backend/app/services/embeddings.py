"""
Embeddings service.

Handles two responsibilities:
  1. Extract raw text from an uploaded document (PDF or plain text).
  2. Chunk that text and embed each chunk using Gemini's embedding model.

Embeddings are stored in two places depending on what is available:
  - Supabase pgvector (production path) — via app.services.retrieval
  - In-memory dict (fallback for demo when Supabase isn't wired up yet)

This dual path means the demo never breaks because the Supabase setup
isn't ready. The MLE work isn't blocked on infrastructure.

Note on inline imports: heavy libs (google.generativeai, PyPDF2, supabase)
are imported inside functions, not at the top. This keeps module load fast
for tests that don't need them, and avoids a circular import with
retrieval.py.

Note on the documents-table path (`_looks_like_uuid` + `_insert_documents_row`):
The Supabase schema in supabase/migrations/0001_initial.sql ties both
documents.user_id and document_chunks.user_id to auth.users(id) — i.e.
they MUST be real UUIDs from Supabase Auth. Our demo uses the literal
string "demo-user" which is not a UUID. So we auto-detect whether the
current user_id looks like a UUID and only go down the full
documents-table path when it does. This keeps demo flows working
identically to today, and the Supabase path activates automatically
once Yousif's auth middleware starts passing real auth.users UUIDs.

Note on append-by-default ingestion (changed from the original ADR):
The in-memory fallback used to wipe a user's chunks on every upload, so
re-uploading replaced the old document. That broke the realistic case
where a user uploads both a resume AND essays — the second upload
would silently nuke the first. We now APPEND on every upload. Callers
that want the old replace-on-upload behavior call clear_user_chunks()
first. The Supabase path still replaces (inside save_chunks_pgvector)
because that's where the production "one resume per auth.user"
invariant lives.
"""
from __future__ import annotations

import io
import logging
import uuid
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

    Supports PDFs (via PyPDF2) and plain text. DOCX support can be added
    later — for the MVP demo, PDF and plain text are enough.

    Whitespace normalization: PyPDF2 (especially on LaTeX-generated PDFs
    like Min's resume) sometimes returns text with every word on its own
    line and odd spacing between characters. That's bad both for what
    Gemini sees in the prompt AND for our log readability (chunks render
    vertically). We collapse all runs of whitespace into single spaces
    before returning. The chunker downstream still splits cleanly via
    its sentence/word fallback separators.
    """
    is_pdf = (
        (content_type and "pdf" in content_type.lower())
        or filename.lower().endswith(".pdf")
    )

    raw: str = ""
    if is_pdf:
        try:
            # Lazy: only load PyPDF2 if the file is actually a PDF.
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            raw = "\n\n".join(pages)
        except Exception as e:
            logger.warning("PDF extraction failed: %s — falling back to raw decode", e)

    if not raw:
        # Plain text fallback (also catches PDF extraction failures).
        try:
            raw = file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # Normalize: collapse any whitespace run (spaces, tabs, newlines) into a
    # single space, then strip outer whitespace. The chunker uses [". ", " ", ""]
    # as fallback separators so word-level splitting still works fine.
    import re
    return re.sub(r"\s+", " ", raw).strip()


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

    # Lazy: same reason as in _configure_gemini_once. Cached after first call.
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


# ── Helpers for the storage path ──────────────────────────────────────────────

def _looks_like_uuid(s: str) -> bool:
    """
    True if `s` is a syntactically valid UUID.

    Used to decide whether to attempt the Supabase `documents` table insert.
    The schema requires user_id to be a real auth.users UUID; "demo-user"
    fails that constraint and would error. Auto-detecting here means demo
    flows keep working and real-auth flows activate transparently once
    Yousif's middleware passes proper UUIDs.
    """
    try:
        uuid.UUID(str(s))
        return True
    except (ValueError, TypeError):
        return False


def _supabase_configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_key)


def _insert_documents_row(
    user_id: str,
    filename: str,
    content_type: str | None,
    document_id: str,
    doc_type: str | None = None,
) -> bool:
    """
    Insert a row into the `documents` table. Returns True on success, False
    on any failure. Failure is logged but not raised — the caller falls
    back to the chunks-only path so the user's upload still works.
    """
    try:
        # Lazy: only load supabase if we actually have keys.
        from supabase import create_client
        client = create_client(settings.supabase_url, settings.supabase_service_key)
        storage_path = f"uploads/{user_id}/{filename}"

        # Replace-by-filename: remove any prior document this user uploaded
        # under the same name, so re-uploading an edited file replaces it
        # instead of duplicating. The FK
        #   document_chunks.document_id references documents(id) on delete cascade
        # means deleting the old documents row also removes its chunks. A
        # differently-named file (e.g. essays.pdf vs resume.pdf) is untouched,
        # so resume + essays coexist.
        client.table("documents").delete() \
            .eq("user_id", user_id).eq("filename", filename).execute()

        client.table("documents").insert({
            "id": document_id,
            "user_id": user_id,
            "filename": filename,
            "content_type": content_type,
            "storage_path": storage_path,
            "doc_type": doc_type,
        }).execute()
        return True
    except Exception as e:
        logger.warning("documents insert failed (%s); falling back to chunks-only", e)
        return False



def clear_user_chunks(user_id: str) -> None:
    """
    Drop all of a user's chunks from the in-memory store.

    Call this BEFORE ingest_document() when you want a new upload to
    replace the user's existing chunks rather than append to them. The
    fake job page does NOT call this — multi-document uploads should add
    to context, not overwrite. A "delete my documents" button on the
    dashboard would call this.

    No-op on the Supabase/pgvector path — that path replaces inside
    save_chunks_pgvector by design, matching the "one resume per
    auth.user" production invariant.
    """
    _MEMORY_STORE.pop(user_id, None)


def clear_user_corpus(user_id: str) -> None:
    """
    Remove ALL of a user's stored documents — both the in-memory store and
    the Supabase/pgvector tables.

    Used by the dashboard's combined upload (wipe-and-rebuild): the client
    clears the corpus once, then re-uploads resume + essays together, so the
    stored set always matches what's currently attached and duplicate /
    stale chunks can't accumulate across re-uploads. Also the basis for a
    "delete all my data" feature.

    The pgvector clear is best-effort: when Supabase isn't configured it
    raises inside _supabase_client, which we swallow — the in-memory clear
    above is the only thing that matters in that case.
    """
    _MEMORY_STORE.pop(user_id, None)
    try:
        from app.services.retrieval import clear_user_chunks_pgvector
        clear_user_chunks_pgvector(user_id)
    except Exception as e:
        logger.info("pgvector clear skipped (%s)", e)

def ingest_document(
    file_bytes: bytes,
    content_type: str | None,
    filename: str,
    user_id: str,
    doc_type: str | None = None,
) -> dict:
    """
    End-to-end ingestion: extract → chunk → embed → store.

    Storage strategy (chosen automatically based on environment):

      1. Supabase configured AND user_id is a real UUID:
         → insert a documents row, then save chunks linked to it.
         → returns stored_in="supabase" and includes document_id.

      2. Supabase configured but user_id is NOT a UUID (e.g. "demo-user"):
         → skip the documents row (would violate the auth.users FK),
           call save_chunks_pgvector(document_id=None) which is allowed
           by the schema.
         → returns stored_in="pgvector".

      3. Supabase NOT configured, or save raises for any reason:
         → fall back to the in-memory store.
         → returns stored_in="memory".

    This keeps demo flows identical to today (path 3 in most local setups)
    while letting the production path light up the moment Yousif's auth
    starts handing the pipeline real Supabase auth.users UUIDs.
    """
    text = extract_text(file_bytes, content_type, filename)
    if not text:
        return {"status": "no_text_extracted", "chunks_stored": 0}

    chunks = chunk_text(text)
    embeddings = embed_texts(chunks)

    document_id: str | None = None
    stored_in = "memory"

    # ── Path 1 / 2: try pgvector ─────────────────────────────────────────────
    if _supabase_configured():
        if _looks_like_uuid(user_id):
            document_id = str(uuid.uuid4())
            inserted = _insert_documents_row(user_id, filename, content_type, document_id, doc_type)
            if not inserted:
                # Drop back to chunks-only — at least retrieval will work.
                document_id = None

        try:
            # Lazy: avoids a circular import; retrieval.py imports from us too.
            from app.services.retrieval import save_chunks_pgvector
            save_chunks_pgvector(
                user_id=user_id,
                chunks=chunks,
                embeddings=embeddings,
                document_id=document_id,
            )
            stored_in = "supabase" if document_id else "pgvector"
        except Exception as e:
            logger.info("pgvector save failed (%s) — using in-memory fallback", e)
            stored_in = "memory"
            document_id = None  # No DB row → don't lie about having one.

    # ── Path 3: in-memory fallback (APPENDS — does not replace) ─────────────
    # Previously this path called .clear() on every upload so re-uploading
    # a resume replaced the old one. That broke the realistic case where
    # a user uploads a resume AND essays: the second upload nuked the
    # first. We now APPEND. Callers who want the old "replace" behavior
    # should call clear_user_chunks(user_id) explicitly first.
    if stored_in == "memory":
        _MEMORY_STORE.setdefault(user_id, []).extend(zip(chunks, embeddings))

    # ─────────────────────────────────────────────────────────────────────────
    # REFERENCE: original Dev path, kept here as a flat "this is what the
    # auto-detected supabase branch above is doing under the hood" explainer.
    # The live logic above already does all of this — auto-detecting whether
    # to take the demo path or the Supabase path based on the runtime
    # environment. Don't uncomment this block; it would double-insert.
    #
    # Kept for two reasons:
    #   1. Future you debugging "why is there a documents row but no chunks
    #      linked to it?" can read this and see the intended shape.
    #   2. If we ever decide to make the Supabase path opt-in via an env
    #      flag instead of auto-detection, this is the recipe to copy.
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
    #         # save_chunks_pgvector now accepts an optional document_id so
    #         # the chunks insert can be linked to this documents row in a
    #         # single call rather than needing a follow-up UPDATE.
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

    summary: dict = {
        "status": "ok",
        "chunks_stored": len(chunks),
        "stored_in": stored_in,
        "preview": chunks[0][:200] if chunks else "",
    }
    if document_id is not None:
        summary["document_id"] = document_id
    return summary


def get_memory_store() -> dict[str, list[tuple[str, list[float]]]]:
    """Exposed so retrieval.py can read the fallback store."""
    return _MEMORY_STORE
