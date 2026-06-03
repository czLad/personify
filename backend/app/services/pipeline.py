"""
The agentic pipeline.

Three-step flow per autofill request:
  1. classify_fields    — Gemini (with heuristic fallback) decides which
                          fields are PERSONAL_STATEMENT vs STANDARD.
  2. retrieve           — for each PERSONAL_STATEMENT field, pull the top-k
                          most relevant chunks from the user's uploaded
                          documents via RAG (pgvector or in-memory).
  3. _generate_response — Gemini writes a ~100 word personalized answer
                          using a prompt variant chosen for the question.

Design notes:

* Confidence threshold (MIN_CONFIDENCE): the classifier returns a
  confidence score per field. We only spend a Gemini generation call when
  the classifier is *sure* the field is a personal statement. Low-confidence
  PERSONAL_STATEMENT verdicts (including all heuristic-fallback results at
  0.6) are skipped — better to leave a field blank than paste an essay
  into a field that wasn't actually open-ended. Promised in Week 4 report.

* Prompt variants: a single one-size-fits-all prompt produces noticeably
  generic output across different question shapes. We pick one of three
  variants based on simple lexical cues in the question:
    - "why ..."  / "what motivates"        → motivation_prompt
    - "describe / tell us about a time"    → story_prompt
    - everything else                      → background_prompt
  This was promised in Week 4 report. The selection is deterministic
  (regex on the question) so the choice is reproducible and testable
  without mocking the LLM.

* The variant name is exposed in the FieldResponse.meta-ish way via the
  `_pick_prompt_variant` return tuple so tests can assert the right
  variant was chosen for a given question.
"""
from __future__ import annotations

import logging
import re

from app.core.llm import get_chat_llm
from app.models.schemas import FieldResponse, FormField
from app.services.classifier import classify_fields
from app.services.retrieval import retrieve

logger = logging.getLogger(__name__)


# ── Tunables ──────────────────────────────────────────────────────────────────

# Below this confidence we don't auto-fill. Heuristic fallback returns 0.6,
# which is intentionally just below the threshold — so when the LLM
# classifier is unavailable we err on the side of leaving fields blank.
# LLM classifications are typically 0.85+ when confident, 0.5–0.7 when
# guessing, which is exactly the line we want to draw.
MIN_CONFIDENCE: float = 0.7

# Used when no auth/user_id is supplied. Real auth (Yousif's work) will
# supply a proper UUID; this keeps the demo working in the meantime.
DEMO_USER_ID = "demo-user"


# ── Prompt variants ───────────────────────────────────────────────────────────
# Three templates, each tuned for a question archetype. All share the same
# {company}/{job_description}/{context}/{question} interface so the rest of
# the pipeline doesn't care which variant was picked.

_BASE_INSTRUCTIONS = (
    "You are writing a personal statement on behalf of a job applicant.\n"
    "Use the applicant's resume excerpts to write an authentic, specific "
    "answer in their voice. Do NOT invent experiences. If the excerpts "
    "are sparse, lean on what you have.\n\n"
    "Company: {company}\n"
    "Job description (truncated):\n{job_description}\n\n"
    "Applicant's resume excerpts:\n{context}\n\n"
    "Application question: {question}\n\n"
)

_MOTIVATION_TEMPLATE = _BASE_INSTRUCTIONS + (
    "Write a single paragraph of ~100 words. Lead with a concrete reason "
    "the applicant is drawn to this specific company or role — name a "
    "product, value, or technical direction from the job description. "
    "Then ground it in one or two specific items from the resume excerpts. "
    "Sound genuinely interested, not corporate. First person. No preamble, "
    "no quotation marks, no headings."
)

_STORY_TEMPLATE = _BASE_INSTRUCTIONS + (
    "Write a single paragraph of ~100 words structured loosely as "
    "situation → action → result. Pick the most concrete example from the "
    "resume excerpts and stay close to it; don't generalize. End on what "
    "the applicant learned or what changed. First person, past tense. "
    "No preamble, no quotation marks, no headings."
)

_BACKGROUND_TEMPLATE = _BASE_INSTRUCTIONS + (
    "Write a single paragraph of ~100 words that synthesizes the resume "
    "excerpts into a coherent picture of who the applicant is and what "
    "they care about. Avoid resume-style bullet points; this should read "
    "as a thoughtful self-description. First person, present tense. No "
    "preamble, no quotation marks, no headings."
)


# Regex cues used to route a question to a variant. Order matters: the first
# match wins. Patterns are intentionally lenient — we'd rather route to a
# reasonable variant than fall through to background for everything.
_MOTIVATION_CUES = re.compile(
    r"\b(why|what (draws|excites|motivates)|interested in|reasons? (you|to)|"
    r"this (role|company|position|team)|fit for)\b",
    re.IGNORECASE,
)
_STORY_CUES = re.compile(
    r"\b(describe a (time|situation|challenge|project|moment)|"
    r"tell us about a (time|situation|challenge|project)|"
    r"give an example|walk us through|"
    r"a time when|when (you|did))\b",
    re.IGNORECASE,
)


def _pick_prompt_variant(question: str) -> tuple[str, str]:
    """
    Choose a prompt template for the given question. Returns (variant_name, template).

    Variant name is returned so callers can log/test which one fired
    without poking into the template string itself.
    """
    if _MOTIVATION_CUES.search(question):
        return "motivation", _MOTIVATION_TEMPLATE
    if _STORY_CUES.search(question):
        return "story", _STORY_TEMPLATE
    return "background", _BACKGROUND_TEMPLATE


# ── LangChain LLM setup ───────────────────────────────────────────────────────

def _get_llm():
    """
    Return a chat LLM tuned for generation (higher temperature).
    Returns None when Gemini isn't configured so the pipeline can fall
    back to placeholder text instead of crashing.
    """
    return get_chat_llm(temperature=0.7)


def _build_generate_chain(variant_template: str):
    """
    Build a LangChain prompt | llm chain for the given variant template.
    Returns the chain or None if Gemini isn't configured.
    """
    llm = _get_llm()
    if llm is None:
        return None

    # Lazy import: see _get_llm.
    from langchain_core.prompts import PromptTemplate

    prompt = PromptTemplate.from_template(variant_template)
    return prompt | llm


# ── Generation ────────────────────────────────────────────────────────────────

def _generate_response(
    question: str,
    company: str,
    job_description: str,
    context_chunks: list[str],
) -> tuple[str, str]:
    """
    Call Gemini through LangChain to generate a personal-statement answer.

    Returns (response_text, variant_name). variant_name is exposed so the
    caller can log or surface which prompt was used.
    """
    variant_name, variant_template = _pick_prompt_variant(question)
    chain = _build_generate_chain(variant_template)

    if chain is None:
        # No API key — return a clear placeholder rather than crashing.
        # We still return a variant_name so tests of the routing logic
        # can verify behavior even with no key set.
        placeholder = (
            f"[Gemini API key not configured. Question was: {question!r}. "
            f"Set GEMINI_API_KEY in backend/.env to enable generation.]"
        )
        return placeholder, variant_name

    context = "\n---\n".join(context_chunks) if context_chunks else "(no resume uploaded yet)"
    job_desc_truncated = (job_description or "(not provided)")[:2000]

    try:
        result = chain.invoke({
            "question": question,
            "company": company or "this company",
            "job_description": job_desc_truncated,
            "context": context,
        })
        text = (result.content if hasattr(result, "content") else str(result)).strip()
        return text, variant_name
    except Exception as e:
        logger.error("generation failed (variant=%s): %s", variant_name, e)
        return f"[Generation failed: {e}]", variant_name


# ── The pipeline entry point ──────────────────────────────────────────────────

def run_autofill_pipeline(
    fields: list[FormField],
    job_description: str,
    company_name: str,
    user_id: str | None = None,
) -> list[FieldResponse]:
    """
    Full classify → retrieve → generate flow.

    Only fields that meet BOTH conditions get a generated response:
      - classification == "PERSONAL_STATEMENT"
      - confidence    >= MIN_CONFIDENCE

    Everything else is silently skipped (no entry in the response list).
    The selector→response mapping is the caller's contract: missing
    selector means "don't fill this one."
    """
    if not fields:
        return []

    user_id = user_id or DEMO_USER_ID

    # ── Step 1: Classify (all fields in one batched call) ────────────────────
    raw_fields = [
        {
            "selector": f.selector,
            "label": f.label,
            "field_type": f.field_type,
        }
        for f in fields
    ]
    classifications = classify_fields(raw_fields)

    # Build a selector → (classification, confidence) lookup so we can apply
    # both the class filter and the confidence threshold in one pass below.
    class_map: dict[str, tuple[str, float]] = {
        c.selector: (c.classification, c.confidence) for c in classifications
    }

    responses: list[FieldResponse] = []
    skipped_low_confidence = 0

    for field in fields:
        classification, confidence = class_map.get(field.selector, ("STANDARD", 0.0))

        if classification != "PERSONAL_STATEMENT":
            continue

        # Confidence gate — promised in Week 4 report.
        if confidence < MIN_CONFIDENCE:
            skipped_low_confidence += 1
            logger.debug(
                "Skipping '%s' due to low confidence %.2f < %.2f",
                field.label, confidence, MIN_CONFIDENCE,
            )
            continue

        # ── Step 2: Retrieve ──────────────────────────────────────────────────
        context_chunks = retrieve(question=field.label, user_id=user_id, k=3)
        logger.info("RETRIEVED for %r:\n%s", field.label,
            "\n---\n".join(c[:120] for c in context_chunks))

        # ── Step 3: Generate ──────────────────────────────────────────────────
        text, variant_name = _generate_response(
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
        logger.debug(
            "Generated for '%s' (variant=%s, confidence=%.2f)",
            field.label, variant_name, confidence,
        )

    logger.info(
        "Pipeline complete: %d fields in, %d filled, %d skipped (low confidence)",
        len(fields), len(responses), skipped_low_confidence,
    )

    return responses
