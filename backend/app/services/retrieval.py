"""
Retrieval service.

Given a question, returns the top-k most relevant chunks from the user's
uploaded documents. Tries pgvector first, falls back to in-memory cosine
similarity if Supabase isn't configured.

This is the R in RAG — the chunks returned here are injected into the
Gemini prompt by app.services.pipeline.

Query boost:
Resumes describe outputs ("Built X using Y"); essays describe decisions
("I chose A over B"). On technical questions, narrative essay chunks
outscore terse resume chunks because they share decision-language
vocabulary. We fold the company name and a truncated job description
into the embedding query so resume chunks get a fair shot. See
_build_query for the construction.

MMR cross-question diversity:
The same chunk (or another chunk from the same experience) tends to
win for multiple questions on the same application — Q1 and Q2 both
get the NASA story, Q3 too. We adapt Maximum Marginal Relevance
(Carbonell & Goldstein, 1998) across questions: chunks already used
in this autofill batch are penalized when scoring candidates for later
questions. See retrieve() and _retrieve_memory_mmr.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from app.core.config import settings
from app.services.embeddings import embed_query, get_memory_store

logger = logging.getLogger(__name__)


# Truncate the job description before mixing it into the query. The question
# is the most important signal; we want the job description to add a few
# topical keywords (e.g. "RAG", "real-time", "distributed") without drowning
# out the question's specifics. 200 chars typically covers the "we are
# building X for Y" lead of a job posting, which is the keyword-densest part.
_JOB_DESCRIPTION_BUDGET = 200


# ── Return type ──────────────────────────────────────────────────────────────

## !!IMPORTANT Class / Struct. Probably the most Important Object for the RAG pipeline
@dataclass
class RetrievedChunk:
    """
    Single chunk returned by retrieve().

    Carries the chunk's embedding alongside its text so the pipeline can
    accumulate "used embeddings" across questions for MMR penalization.
    `score` is the post-penalty similarity (or pre-penalty if no penalize
    list was supplied). Empty `embedding` means the chunk came from the
    pgvector path, which does not yet surface embeddings — those chunks
    can't feed the next round's MMR penalty until the pgvector RPC is
    upgraded (see commented block below).
    """
    content: str
    embedding: list[float] = field(default_factory=list)
    score: float = 0.0


# ── Query construction ───────────────────────────────────────────────────────

def _build_query(question: str, company: str = "", job_description: str = "") -> str:
    """
    Build the query string fed to embed_query.

    Concatenates the question with the company name and a truncated job
    description. The result is what gets embedded for similarity search
    against the user's uploaded chunks.

    Why this matters (see module docstring for full context):
    Adding job-specific vocabulary to the query lets technical resume
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

    APPENDS — does not wipe the user's existing chunks. This mirrors the
    in-memory path (ingest_document appends by default), so uploading a
    resume and then essays accumulates both instead of the second upload
    clobbering the first.

    Replace-on-re-upload is handled one level up, in
    embeddings._insert_documents_row: before inserting a new `documents`
    row it deletes any prior row with the same (user_id, filename), and the
    `document_chunks.document_id ... on delete cascade` FK removes that
    document's old chunks. So re-uploading an edited resume.pdf replaces
    its chunks without duplicating, while a differently-named essays.pdf
    is left untouched.

    For the relaxed-schema demo path (document_id is None, no documents
    row), there is no filename-scoped cascade, so this function pure-appends
    — same behavior as the in-memory store. Use clear_user_chunks_pgvector
    to wipe explicitly when you want a clean slate.

    `document_id` is optional. When None, the chunk's document_id column is
    left null. When set (the authenticated path), every chunk row is linked
    to its parent `documents` row.
    """
    client = _supabase_client()

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


def clear_user_chunks_pgvector(user_id: str) -> None:
    """
    Delete all of a user's documents and chunks from Supabase. Parity with
    the in-memory clear_user_chunks. Not called on the normal upload path
    (uploads append); used by clear_user_corpus for the dashboard's
    wipe-and-rebuild and a future "delete all my data" feature.

    Deletes the `documents` rows first — the
    `document_chunks.document_id ... on delete cascade` FK removes their
    chunks. Then deletes any remaining chunks not tied to a documents row
    (the relaxed-schema demo path, where document_id is null).
    """
    client = _supabase_client()
    client.table("documents").delete().eq("user_id", user_id).execute()
    client.table("document_chunks").delete().eq("user_id", user_id).execute()


def _retrieve_pgvector(user_id: str, query_embedding: list[float], k: int) -> list[str]:
    """
    Query pgvector for top-k chunks by cosine distance.

    Uses a stored RPC for safety. If the RPC doesn't exist yet, this raises
    and the caller falls back to in-memory.

    Note: this path does NOT apply the MMR penalty. The RPC's return shape
    doesn't currently include embeddings, so we can't feed the next-round
    penalty pool. The commented block below sketches the MMR-enabled
    version we'll switch to when pgvector is wired in production.
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


# ── pgvector MMR (planned, not yet active) ───────────────────────────────────
# When we promote pgvector to the live path, we'll need the chunk
# embeddings back from the RPC so we can apply the same MMR penalty math
# that _retrieve_memory_mmr applies below. Two options:
#
#   (a) Add the penalty math to a new SQL RPC `match_document_chunks_mmr`
#       that takes the penalize embeddings as a parameter. Pure-DB and
#       fast, but writing PL/pgSQL for cosine math is annoying.
#   (b) Have the existing RPC also return each row's embedding. Over-pull
#       k*3 candidates from the DB, then apply the penalty client-side
#       (same code path as in-memory). Slower over the wire but the math
#       lives in one place. Recommended.
#
# Sketch of option (b) — uncomment and adapt when migrating:
#
# def _retrieve_pgvector_mmr(
#     user_id: str,
#     query_embedding: list[float],
#     k: int,
#     *,
#     penalize: list[list[float]] | None,
#     penalty_weight: float,
# ) -> list[RetrievedChunk]:
#     client = _supabase_client()
#     response = client.rpc(
#         "match_document_chunks_with_embeddings",  # new RPC: returns content + embedding
#         {
#             "query_embedding": query_embedding,
#             "match_user_id": user_id,
#             "match_count": k * 3,  # over-pull so MMR has room to re-rank
#         },
#     ).execute()
#     rows = response.data or []
#     if not rows:
#         return []
#
#     scored: list[RetrievedChunk] = []
#     for row in rows:
#         emb = row["embedding"]
#         q_sim = _cosine_similarity(query_embedding, emb)
#         if penalize:
#             max_pen = max(_cosine_similarity(emb, p) for p in penalize)
#             final = q_sim - penalty_weight * max_pen
#         else:
#             final = q_sim
#         scored.append(RetrievedChunk(content=row["content"], embedding=emb, score=final))
#
#     scored.sort(key=lambda c: c.score, reverse=True)
#     return scored[:k]


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

## !!IMPORTANT FUNCTION FOR MMR
def _retrieve_memory_mmr(
    user_id: str,
    query_embedding: list[float],
    k: int,
    *,
    penalize: list[list[float]] | None,
    penalty_weight: float,
) -> list[RetrievedChunk]:
    """
    Retrieve top-k chunks from the in-memory store with an MMR-style
    cross-question diversity penalty.

    Scoring formula:
        score(c) = sim(c, query)  −  penalty_weight · max_{u in penalize} sim(c, u)

    This is the Carbonell-Goldstein MMR (1998) formula in subtractive
    form. The classical formulation weights both terms with λ summing
    to 1; we use a single scalar (penalty_weight ≈ 1 − λ) because that
    knob is easier to think about. Setting penalty_weight=0 reproduces
    pure relevance.

    `penalize` is the list of embeddings of chunks already chosen for
    earlier questions in this autofill batch. When None or empty, this
    function is equivalent to plain top-k cosine similarity.
    """
    store = get_memory_store()
    rows = store.get(user_id, [])
    if not rows:
        return []

    penalize_pool = penalize or []

    scored: list[RetrievedChunk] = []
    for chunk, emb in rows:
        q_sim = _cosine_similarity(query_embedding, emb)
        if penalize_pool:
            max_pen = max(_cosine_similarity(emb, p) for p in penalize_pool)
            final = q_sim - penalty_weight * max_pen
        else:
            final = q_sim
        scored.append(RetrievedChunk(content=chunk, embedding=emb, score=final))

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:k]


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve(
    question: str,
    user_id: str,
    k: int = 3,
    *,
    company: str = "",
    job_description: str = "",
    penalize: list[list[float]] | None = None,
    penalty_weight: float = 0.4,
) -> list[RetrievedChunk]:
    """
    Return up to k chunks most relevant to the question.

    Two retrieval-quality improvements layered on plain top-k:

    1. Query boost: the string embedded for similarity search is the
       question concatenated with company name and a truncated job
       description. See _build_query.

    2. Cross-question MMR (in-memory path only, for now): when `penalize`
       is supplied, each candidate's similarity score is reduced by
       `penalty_weight * max_sim(candidate, penalize)` before ranking.
       This pushes chunks already used for earlier questions out of the
       top-k for later ones. See _retrieve_memory_mmr.

    The pgvector path does NOT apply MMR yet (the current RPC doesn't
    return embeddings, so we can't surface them for the next round's
    penalty pool). When pgvector is promoted to the live path, swap in
    the MMR-enabled version sketched in the commented block above.

    Returns a list of RetrievedChunk; the pipeline uses .content for the
    LLM prompt and .embedding to feed the next call's penalize pool.
    """
    query = _build_query(question, company, job_description)
    query_embedding = embed_query(query)

    # Pgvector path (no MMR yet — see module docstring + commented block).
    try:
        chunks = _retrieve_pgvector(user_id, query_embedding, k)
        if chunks:
            # Wrap in the RetrievedChunk shape so the caller doesn't have
            # to branch. Empty `embedding` signals "can't be used for the
            # next MMR round" — the pipeline filters these out.
            return [RetrievedChunk(content=c, embedding=[], score=0.0) for c in chunks]
    except Exception as e:
        logger.info("pgvector retrieval unavailable (%s) — using memory store", e)

    return _retrieve_memory_mmr(
        user_id,
        query_embedding,
        k,
        penalize=penalize,
        penalty_weight=penalty_weight,
    )
