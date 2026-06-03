"""
Retrieval service.

Given a question, returns the top-k most relevant chunks from the user's
uploaded documents. Tries pgvector first, falls back to in-memory cosine
similarity if Supabase isn't configured.

This is the R in RAG — the chunks returned here are injected into the
Gemini prompt by app.services.pipeline.

Query boost (added in Week 7):
Resumes describe outputs ("Built X using Y"); essays describe decisions
("I chose A over B because"). When the user's question is something like
"Describe a time you faced a tradeoff," essay chunks naturally outscore
resume chunks because they share decision-language vocabulary. To let
resume chunks compete on their actual technical content, retrieve() now
accepts the company name and job description as optional kwargs and
folds them into the embedding query — see _build_query. The behavior is
backward-compatible: callers that don't pass company/job_description get
the old "question-only" embedding, just with longer signatures.
"""
from __future__ import annotations

import logging
import math

from app.core.config import settings
from app.services.embeddings import embed_query, get_memory_store

logger = logging.getLogger(__name__)


# Truncate the job description before mixing it into the query. The question
# is the most important signal; we want the job description to add a few
# topical keywords (e.g. "RAG", "real-time", "distributed") without drowning
# out the question's specifics. 200 chars typically covers the "we are
# building X for Y" lead of a job posting, which is the keyword-densest part.
_JOB_DESCRIPTION_BUDGET = 200


# ── Query construction ───────────────────────────────────────────────────────

def _build_query(question: str, company: str = "", job_description: str = "") -> str:
    """
    Build the query string fed to embed_query.

    Concatenates the question with the company name and a truncated job
    description. The result is what gets embedded for similarity search
    against the user's uploaded chunks.

    Why this matters (see module docstring for full context):
    Adding role-specific vocabulary to the query lets technical resume
    chunks score competitively against narrative essay chunks for
    technical questions.

    Args:
        question: the field's label / question text. Always included.
        company: company name. Skipped if empty.
        job_description: job posting text. Truncated to
            _JOB_DESCRIPTION_BUDGET chars to keep the question dominant
            in the embedding. Skipped if empty.

    Exposed (not underscore-prefixed strictly) so tests can assert on
    the string construction without mocking the embedder. Treat it as
    internal regardless.
    """
    parts = [question]
    if company:
        parts.append(company)
    if job_description:
        parts.append(job_description[:_JOB_DESCRIPTION_BUDGET])
    return " ".join(p.strip() for p in parts if p and p.strip())


# ── Pgvector path ─────────────────────────────────────────────────────────────

def _supabase_client():
    """Lazy import + construct so missing creds don't break module import."""
    if not (settings.supabase_url and settings.supabase_service_key):
        raise RuntimeError("Supabase not configured")
    # Lazy: supabase package is heavy and unnecessary when running in
    # the in-memory demo mode.
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_service_key)


def save_chunks_pgvector(
    user_id: str,
    chunks: list[str],
    embeddings: list[list[float]],
    document_id: str | None = None,
) -> None:
    """
    Persist chunks + embeddings to Supabase's document_chunks table.

    Design notes:
    * Replaces any existing chunks for this user (re-uploading = replacing).
      This is per our DECISIONS.md — a user has one active resume at a time.
    * `document_id` is optional. When None, the chunk's document_id column
      is left null (allowed by the schema). This is what happens during the
      demo phase. Once Yousif's auth lands and ingest_document starts
      passing a real UUID, every chunk row will be linked to its parent
      `documents` row, which enables features like "delete this resume"
      or "which resume did this chunk come from".
    """
    client = _supabase_client()

    # Wipe existing chunks for this user (re-uploading replaces, per ADR).
    client.table("document_chunks").delete().eq("user_id", user_id).execute()

    rows: list[dict] = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        row: dict = {
            "user_id": user_id,
            "chunk_index": i,
            "content": chunk,
            "embedding": emb,
        }
        # Only include document_id when we actually have one. Omitting the
        # key (rather than sending null) keeps the supabase-py payload tidy
        # and lets Postgres apply its DEFAULT if any.
        if document_id is not None:
            row["document_id"] = document_id
        rows.append(row)

    if rows:
        client.table("document_chunks").insert(rows).execute()


def _retrieve_pgvector(user_id: str, query_embedding: list[float], k: int) -> list[str]:
    """
    Query pgvector for top-k chunks by cosine distance.

    Uses a stored RPC for safety. If the RPC doesn't exist yet, this raises
    and the caller falls back to in-memory.
    """
    client = _supabase_client()
    response = client.rpc(
        "match_document_chunks",
        {
            "query_embedding": query_embedding,
            "match_user_id": user_id,
            "match_count": k,
        },
    ).execute()
    return [row["content"] for row in (response.data or [])]


# ── In-memory fallback path ───────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _retrieve_memory(user_id: str, query_embedding: list[float], k: int) -> list[str]:
    store = get_memory_store()
    rows = store.get(user_id, [])
    if not rows:
        return []

    scored = [
        (_cosine_similarity(query_embedding, emb), chunk)
        for chunk, emb in rows
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:k]]


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve(
    question: str,
    user_id: str,
    k: int = 3,
    *,
    company: str = "",
    job_description: str = "",
) -> list[str]:
    """
    Return up to k chunks most relevant to the question.

    The query embedded for similarity search is NOT just the question —
    it's the question concatenated with the company name and a truncated
    job description (see _build_query). This biases retrieval toward
    chunks that share vocabulary with the specific role, which helps
    resume chunks compete with essay chunks on technical questions.

    `company` and `job_description` are keyword-only and default to "".
    Passing empty strings reproduces the pre-Week 7 behavior exactly.

    Tries pgvector; on any failure (not configured, RPC missing, network,
    no chunks for this user there), falls back to the in-memory store
    populated during ingestion. If both come up empty, returns [].
    """
    query = _build_query(question, company, job_description)
    query_embedding = embed_query(query)

    try:
        chunks = _retrieve_pgvector(user_id, query_embedding, k)
        if chunks:
            return chunks
    except Exception as e:
        logger.info("pgvector retrieval unavailable (%s) — using memory store", e)

    return _retrieve_memory(user_id, query_embedding, k)