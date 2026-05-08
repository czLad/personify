"""
The agentic pipeline.

This is the brain of Personify. The extension's content script handles
perceive (DOM scan) and act (paste). This module handles decide:

  1. Classify   — for each form field, is this a personal statement question?
  2. Retrieve   — for personal-statement fields, fetch relevant chunks from
                  the user's resume and past essays via RAG (pgvector).
  3. Generate   — hand the question + chunks + job context to Gemini, get
                  back a personalized 100-word response.

The classifier is a cheap keyword pre-filter followed by an LLM check, so
we avoid burning tokens on obviously-standard fields like "First Name."

LangChain is used for prompt templating and the LLM wrapper. The RAG
retrieval is a plain function call rather than a LangChain Retriever
because it needs to be aware of the user_id from the request context,
which is awkward to thread through a LangChain chain.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.models.schemas import FieldResponse, FormField
from app.services.retrieval import retrieve

logger = logging.getLogger(__name__)


# ── Cheap keyword pre-filter ──────────────────────────────────────────────────
# These keywords catch ~80% of personal statement questions without an LLM
# call. The LLM verifies borderline cases below.

_OBVIOUS_PERSONAL_STATEMENT_KEYWORDS = (
    "why do you want",
    "why are you interested",
    "why this company",
    "why should we",
    "tell us about",
    "describe a time",
    "describe a challenge",
    "what motivates",
    "what excites",
    "cover letter",
    "personal statement",
    "your interest in",
    "fit for this role",
)

_OBVIOUS_STANDARD_KEYWORDS = (
    "first name",
    "last name",
    "full name",
    "email",
    "phone",
    "address",
    "city",
    "state",
    "zip",
    "country",
    "linkedin",
    "github",
    "website",
    "portfolio",
    "school",
    "university",
    "gpa",
    "graduation",
    "degree",
    "years of experience",
    "salary",
    "start date",
    "available",
    "authorized",
    "sponsorship",
    "visa",
    "race",
    "gender",
    "ethnicity",
    "veteran",
    "disability",
)


def _quick_classify(label: str) -> str | None:
    """
    Returns 'PERSONAL_STATEMENT', 'STANDARD', or None if uncertain.
    None means: defer to the LLM classifier.
    """
    lower = label.lower()
    if any(kw in lower for kw in _OBVIOUS_PERSONAL_STATEMENT_KEYWORDS):
        return "PERSONAL_STATEMENT"
    if any(kw in lower for kw in _OBVIOUS_STANDARD_KEYWORDS):
        return "STANDARD"
    return None


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

def _build_classify_chain():
    """
    LLM-based classifier for fields the keyword filter couldn't decide.
    Returns a LangChain chain or None if Gemini isn't configured.
    """
    llm = _get_llm()
    if llm is None:
        return None

    from langchain_core.prompts import PromptTemplate

    prompt = PromptTemplate.from_template(
        "You classify form fields on a job application page.\n"
        "Given a field's label, decide if it is a personal statement question "
        "(an open-ended question expecting an essay-style answer about the "
        "applicant) or a standard field (name, email, GPA, dropdowns, etc.).\n\n"
        "Field label: \"{label}\"\n\n"
        "Reply with exactly one word: PERSONAL_STATEMENT or STANDARD."
    )
    return prompt | llm


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

def _llm_classify(label: str) -> str:
    """Use Gemini to classify a field whose label was ambiguous."""
    chain = _build_classify_chain()
    if chain is None:
        # No API key: be conservative, treat as STANDARD so we don't paste an essay.
        return "STANDARD"
    try:
        result = chain.invoke({"label": label})
        text = (result.content if hasattr(result, "content") else str(result)).strip().upper()
        return "PERSONAL_STATEMENT" if "PERSONAL_STATEMENT" in text else "STANDARD"
    except Exception as e:
        logger.warning("classify fallback (%s)", e)
        return "STANDARD"


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
    Full classify → retrieve → generate pipeline.
    """
    user_id = user_id or DEMO_USER_ID
    responses: list[FieldResponse] = []

    for field in fields:
        # 1. Classify (cheap filter first, then LLM if needed)
        classification = _quick_classify(field.label) or _llm_classify(field.label)
        if classification != "PERSONAL_STATEMENT":
            continue

        # 2. Retrieve
        context_chunks = retrieve(question=field.label, user_id=user_id, k=3)

        # 3. Generate
        text = _generate_response(
            question=field.label,
            company=company_name,
            job_description=job_description,
            context_chunks=context_chunks,
        )

        responses.append(FieldResponse(
            selector=field.selector,
            response=text,
            classification="PERSONAL_STATEMENT",
        ))

    return responses