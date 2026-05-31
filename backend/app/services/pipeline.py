"""
The agentic pipeline.

This module is intentionally a stub right now. The real implementation
will use LangChain to chain three steps:

  1. classify_fields    —  Gemini decides which fields need a personal statement response.
  2. retrieve_context   — pgvector returns relevant chunks from the user's docs
  3. generate_response  — Gemini writes a personalized response per field

For now we return a deterministic mock so the extension and frontend can
develop against a stable contract.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.models.schemas import FieldResponse, FormField
from app.services.retrieval import retrieve
from app.services.classifier import classify_fields


logger = logging.getLogger(__name__)

# ── LangChain LLM setup ───────────────────────────────────────────────────────

def _get_llm():
    """Lazily build the Gemini LLM. Returns None if no API key configured."""
    if not settings.gemini_api_key:
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.7,
    )


# ── LangChain prompts ─────────────────────────────────────────────────────────


def _build_generate_chain():
    """
    Builds the LangChain prompt chain for personal statement generation.
    Returns the chain or None if Gemini isn't configured.
    """
    llm = _get_llm()
    if llm is None:
        return None

    from langchain_core.prompts import PromptTemplate

    prompt = PromptTemplate.from_template(
        "You are writing a personal statement on behalf of a job applicant.\n"
        "Use the applicant's resume excerpts to write an authentic, specific "
        "answer in their voice. Do NOT invent experiences. If the excerpts "
        "are sparse, lean on what you have.\n\n"
        "Company: {company}\n"
        "Job description (truncated):\n{job_description}\n\n"
        "Applicant's resume excerpts:\n{context}\n\n"
        "Application question: {question}\n\n"
        "Write a single paragraph response of approximately 100 words. "
        "First person. No preamble, no quotation marks, no headings — just "
        "the answer itself."
    )
    return prompt | llm


# ── Helpers ───────────────────────────────────────────────────────────────────


def _generate_response(
    question: str,
    company: str,
    job_description: str,
    context_chunks: list[str],
) -> str:
    """Call Gemini through LangChain to generate a personal-statement answer."""
    chain = _build_generate_chain()

    if chain is None:
        # No API key — return a clear placeholder rather than crashing.
        return (
            f"[Gemini API key not configured. Question was: {question!r}. "
            f"Set GEMINI_API_KEY in backend/.env to enable generation.]"
        )

    context = "\n---\n".join(context_chunks) if context_chunks else "(no resume uploaded yet)"
    job_desc_truncated = (job_description or "(not provided)")[:2000]

    try:
        result = chain.invoke({
            "question": question,
            "company": company or "this company",
            "job_description": job_desc_truncated,
            "context": context,
        })
        return (result.content if hasattr(result, "content") else str(result)).strip()
    except Exception as e:
        logger.error("generation failed: %s", e)
        return f"[Generation failed: {e}]"


# ── The pipeline entry point ──────────────────────────────────────────────────

# A demo user_id used when auth isn't yet wired. Yousif will swap this out
# for the real authenticated user_id once the auth middleware is done.
DEMO_USER_ID = "demo-user"


def run_autofill_pipeline(
    fields: list[FormField],
    job_description: str,
    company_name: str,
    user_id: str | None = None,
) -> list[FieldResponse]:
    """
    classify → [retrieve] → [generate]

    Classify step is now live (Gemini via LangChain with heuristic fallback).
    Retrieve + generate are stubs pending pgvector integration.
    """
    if not fields:
        return []
    
    user_id = user_id or DEMO_USER_ID

    # ── Step 1: Classify ──────────────────────────────────────────────────────
    raw_fields = [
        {
            "selector": f.selector,
            "label": f.label,
            "field_type": f.field_type,
        }
        for f in fields
    ]

    classifications = classify_fields(raw_fields)

    # Build a quick lookup: selector → classification
    class_map = {c.selector: c.classification for c in classifications}

    responses: list[FieldResponse] = []

    for field in fields:
        if class_map.get(field.selector, "STANDARD") != "PERSONAL_STATEMENT":
            continue

        # 2. Retrieve
        context_chunks = retrieve(question=field.label, user_id=user_id, k=3)

        # 3. Generate
        text = _generate_response(
            question=field.label,
            company=company_name or "this company",
            job_description=job_description,
            context_chunks=context_chunks,
        )

        responses.append(FieldResponse(
            selector=field.selector,
            response=text,
            classification="PERSONAL_STATEMENT",
        ))
        logger.debug("Field '%s' classified as PERSONAL_STATEMENT", field.label)

    logger.info(
        "Pipeline complete: %d fields in, %d personal statement fields out",
        len(fields),
        len(responses),
    )

    return responses