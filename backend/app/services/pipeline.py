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
  into a field that wasn't actually open-ended.

* Prompt variants: a single one-size-fits-all prompt produces noticeably
  generic output across different question shapes. We pick one of three
  variants based on simple lexical cues in the question:
    - "why ..."  / "what motivates"        → motivation_prompt
    - "describe / tell us about a time"    → story_prompt
    - everything else                      → background_prompt
The selection is deterministic (regex on the
  question) so the choice is reproducible and testable without the LLM.

* Query boost: company name + truncated job description folded
  into the embedding query. Resume bullets compete with essay prose on
  technical questions. See retrieval._build_query.

* Cross-question MMR: chunks used for earlier questions in the
  same autofill batch are penalized when scoring candidates for later
  ones. This stops the LLM from telling the same NASA story for both
  "why this company" and "describe a tradeoff." Implementation: pipeline
  keeps a `used_embeddings` list across its field loop, passes it as
  `penalize` to retrieve(). See retrieval._retrieve_memory_mmr.

* Variant + retrieved chunks + formatted prompt are logged at INFO level
  per field so we can audit what the LLM actually saw. Requires
  logging.basicConfig(level=logging.INFO) at app startup — see main.py.
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

# How many chunks to retrieve per question.
#
# Tuned for our resume+essays corpus shape (~30 chunks total per user
# during the demo). At k=3 a single dominant topic in the essays can
# crowd out resume content entirely. At k=6+ the context window starts
# carrying marginal-relevance chunks that dilute the prompt. 4 gives
# the LLM enough breadth to mix resume facts with essay narrative
# without overwhelming it.
RETRIEVAL_K: int = 4

# MMR cross-question diversity weight. Subtracted from each candidate
# chunk's query similarity, scaled by its max similarity to chunks
# already used in this autofill batch. See retrieval._retrieve_memory_mmr
# for the full formula.
#
# 0.4 is tuned for a ~30-chunk demo corpus with 3 personal-statement
# questions per application. Higher (0.5–0.6) gives stronger diversity
# but can demote a genuinely-perfect-fit chunk on its second appearance.
# Lower (0.2–0.3) is gentler. Plays the role of (1 − λ) in the classical
# Carbonell-Goldstein MMR formulation.
MMR_PENALTY_WEIGHT: float = 0.4

# Generation temperature.
#
# History of tuning:
#   0.7  — initial. Good prose, but the LLM ignored structural rules
#          (didn't follow show-then-state, kept generic closers).
#   0.5  — too cold. Followed rules but produced choppy, staccato prose
#          with no narrative connective tissue. Q2 dove straight into
#          "Our key API endpoints..." with no scene-setting.
#   0.65 — current sweet spot. Restores narrative rhythm while still
#          respecting the structural rules in _BASE_INSTRUCTIONS.
# If essays become unstructured again, drop back to 0.6 before going lower.
GENERATION_TEMPERATURE: float = 0.65

# Used when no auth/user_id is supplied. Real auth (Yousif's work) will
# supply a proper UUID; this keeps the demo working in the meantime.
DEMO_USER_ID = "demo-user"


# ── Prompt variants ───────────────────────────────────────────────────────────
# Three templates, each tuned for a question archetype. All share the same
# {company}/{job_description}/{context}/{question} interface so the rest of
# the pipeline doesn't care which variant was picked.
#
# Rules applied to all three (in _BASE_INSTRUCTIONS):
#   - Persona: "a thoughtful applicant writing in your own voice." Frames
#     the LLM as a person speaking, not a marketing copywriter. Helps
#     restore narrative texture that the previous (rule-heavy) prompt
#     stripped out.
#   - Concrete-detail requirement: every response must name >=2 specific
#     items from the resume excerpts. Generic claims about character or
#     values without a concrete anchor are not allowed. This kills the
#     "I'm passionate about optimal algorithm design" filler pattern.
#   - Sentence-rhythm rule: most sentences between 8 and 25 words. Bans
#     both run-ons (the old failure mode) and choppy fragments (the
#     overcorrected one). Aims for a recruiter-readable rhythm.
#   - Subtle-alignment guard: blocklist on glue phrases ("aligns with",
#     "I'm drawn to") AND on promotional closers ("I am eager to",
#     "impactful software that ships"). Ban on verbatim quoting of the
#     JD. The model otherwise substitutes one cliché for another.
#   - Aspiration guard: phrases like "I would like to" / "I hope to" in
#     the corpus are NOT to be claimed as completed experience. This
#     prevents the model from reading aspirational essay content and
#     reporting it as fact.
# Variant-specific:
#   - motivation : show a concrete detail first, save company mention
#                  for at most the final sentence.
#   - story      : open with scene-setting (project, role, stakes), then
#                  decision → result → learning. ~120 words. Do NOT
#                  name the company.
#   - background : open with a specific moment/person/experience, end on
#                  a forward-looking note that hints at fit WITHOUT
#                  naming the company.

_BASE_INSTRUCTIONS = (
    "You are a thoughtful applicant writing in your own voice. You tell "
    "short, specific stories that quietly demonstrate your fit. You "
    "write like a person speaking — not a press release, not a string "
    "of resume bullets.\n\n"
    "Use the applicant's resume excerpts to write an authentic, specific "
    "answer in their voice. Do NOT invent experiences — if the excerpts "
    "don't contain something to support a claim, leave the claim out.\n\n"
    "Hard rules for every response:\n"
    "  - Reference at least TWO specific items from the resume excerpts. "
    "Specific means a project name, a technology, a place, a number, or "
    "a named experience. Generic claims about the applicant's values or "
    "character that don't tie to a concrete item are not allowed.\n"
    "  - Vary sentence length naturally. Most sentences should land "
    "between 8 and 25 words. Avoid long sentences with stacked "
    "subordinate clauses. Avoid the opposite extreme too — a wall of "
    "choppy 5-word sentences reads as nervous, not confident. Aim for "
    "a rhythm a recruiter could read aloud.\n"
    "  - Do not use the phrases 'aligns with', 'perfectly matches', "
    "'I'm drawn to', or 'I am particularly drawn to'. Avoid generic "
    "closing phrases like 'I am eager to contribute', 'I am excited to', "
    "'impactful software that ships', or similar promotional clichés. "
    "Do not quote the job description verbatim. The alignment should be "
    "visible from what you describe, not announced. End on a specific "
    "forward-looking thought tied to the work you described, not a "
    "stock applicant closer.\n"
    "  - If the excerpts describe aspirations (phrasings like 'I would "
    "like to', 'I hope to', 'I want to', 'I plan to', 'I intend to'), "
    "treat them as aspirations, not completed experiences. Do not claim "
    "them as things the applicant has already done.\n"
    "  - You may use one paragraph break if the response has two "
    "distinct beats (e.g., past experience → present focus, or "
    "decision → reflection). Otherwise stay in one paragraph. No "
    "headings, no bullet points.\n\n"
    "Company: {company}\n"
    "Job description (truncated):\n{job_description}\n\n"
    "Applicant's resume excerpts:\n{context}\n\n"
    "Application question: {question}\n\n"
)

_MOTIVATION_TEMPLATE = _BASE_INSTRUCTIONS + (
    "Open with one specific detail from the resume excerpts that shows "
    "the applicant's fit for this kind of work. Use that as the entry "
    "point — a vivid opening, not a thesis statement.\n\n"

    "After the opening, anchor to the TECHNICAL_SKILLS and ROLE_FOCUS "
    "from the extracted signals — paraphrased, not quoted verbatim. "
    "The MISSION and CULTURAL_VALUES should inform the tone and "
    "direction — not as flattery, but as internalized context. The "
    "response should feel like it was written by someone who has read "
    "and understood what this company is building. Engaging with what "
    "the work IS is encouraged; flattering who the employer is, is not.\n\n"

    "If you have knowledge of {company} from your training data, use "
    "it as soft background context — but only if highly confident. "
    "If uncertain, rely only on the extracted signals above. Never "
    "state company facts not supported by the signals or high-confidence "
    "training knowledge.\n\n"

    "Only reference experiences from the resume excerpts. Save the "
    "company name for the final sentence at most. First person, present "
    "tense. Aim for 150–200 words, target around 180. Single paragraph. "
    "No preamble, no quotation marks, no headings."
)



_STORY_TEMPLATE = _BASE_INSTRUCTIONS + (
    "Aim for 150–210 words, target around 180. If you can land the "
    "answer cleanly in 160, do — don't pad to fill the range. One "
    "paragraph is fine; use a single paragraph break if the decision "
    "and the reflection feel like distinct beats. Open with 1–2 "
    "sentences that set the scene: name the project or place, briefly "
    "say what you were building or what role you held, and what was "
    "at stake. Then describe the tradeoff you faced and what you "
    "chose. Then what happened and what you learned. The opening is "
    "context, not the answer — give the reader enough to place you "
    "before the decision lands. Pick the most concrete example from "
    "the resume excerpts and stay close to it; do not generalize. "
    "Do NOT name the company; this is about the applicant's "
    "experience, not the application. First person, past tense. "
    "No preamble, no quotation marks, no headings."
)

_BACKGROUND_TEMPLATE = _BASE_INSTRUCTIONS + (
    "Open with a specific moment, person, or experience from the resume "
    "excerpts that shaped the applicant. Use that as the entry point. "
    "Then connect it to what the applicant cares about and wants to "
    "build. End on a forward-looking note that hints at fit WITHOUT "
    "naming the company. Do NOT name the company. First person, present "
    "tense. Aim for 130–180 words, target around 150. If you can land "
    "the answer cleanly in 140, do — don't pad to fill the range. One "
    "paragraph is the default; use a single paragraph break if there's "
    "a clean 'shaped by X → now I care about Y' arc that benefits from "
    "one. No preamble, no quotation marks, no headings."
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
    Return a chat LLM tuned for generation. Temperature is intentionally
    moderate — see GENERATION_TEMPERATURE rationale above. Returns None
    when Gemini isn't configured so the pipeline can fall back to
    placeholder text instead of crashing.
    """
    return get_chat_llm(temperature=GENERATION_TEMPERATURE)


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

    # Format the prompt manually first so we can log exactly what Gemini
    # sees. variant_template is a plain string with {placeholders}; .format
    # produces the same string LangChain's PromptTemplate would build.
    # Logging this is the single most useful debugging tool when an essay
    # comes back wrong — you can see whether the prompt or the model is
    # at fault. Requires logging.basicConfig(level=INFO) at app startup.
    prompt_inputs = {
        "question": question,
        "company": company or "this company",
        "job_description": job_desc_truncated,
        "context": context,
    }
    formatted_prompt = variant_template.format(**prompt_inputs)
    logger.info(
        "PROMPT (variant=%s) for %r:\n%s\n",
        variant_name, question, formatted_prompt,
    )

    try:
        result = chain.invoke(prompt_inputs)
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

    Cross-question MMR: this function maintains a `used_embeddings` list
    across its per-field loop. After each retrieve() call, the embeddings
    of the selected chunks are appended. Subsequent retrieve() calls in
    the same batch receive that list as `penalize`, so chunks already
    used for earlier questions score lower for later ones. The first
    field's retrieve() is unpenalized (empty pool).
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

    # MMR penalty pool: embeddings of chunks already chosen this batch.
    # Empty on the first field. Grows as we retrieve.
    used_embeddings: list[list[float]] = []

    for field in fields:
        classification, confidence = class_map.get(field.selector, ("STANDARD", 0.0))

        if classification != "PERSONAL_STATEMENT":
            continue

        # Confidence gate — promised in report.
        if confidence < MIN_CONFIDENCE:
            skipped_low_confidence += 1
            logger.debug(
                "Skipping '%s' due to low confidence %.2f < %.2f",
                field.label, confidence, MIN_CONFIDENCE,
            )
            continue

        # ── Step 2: Retrieve ──────────────────────────────────────────────────
        # Query boost: company + job description folded into the embedding
        # query (see retrieval._build_query).
        # MMR: used_embeddings from earlier fields demote chunks about the
        # same experience (see retrieval._retrieve_memory_mmr).
        # Pass a copy of used_embeddings, not the live list — we mutate
        # it after this call and don't want the retrieve() implementation
        # (or test mocks capturing the call) to see post-mutation state.
        retrieved = retrieve(
            question=field.label,
            user_id=user_id,
            k=RETRIEVAL_K,
            company=company_name or "",
            job_description=job_description or "",
            penalize=list(used_embeddings) if used_embeddings else None,
            penalty_weight=MMR_PENALTY_WEIGHT,
        )
        context_chunks = [r.content for r in retrieved]
        logger.info(
            "RETRIEVED for %r (penalize_pool=%d):\n%s",
            field.label,
            len(used_embeddings),
            "\n---\n".join(c[:120] for c in context_chunks),
        )

        # Add these chunks' embeddings to the penalty pool for subsequent
        # fields. Skip empty embeddings — those came from the pgvector
        # path which doesn't surface embeddings yet (see retrieval.py).
        for r in retrieved:
            if r.embedding:
                used_embeddings.append(r.embedding)

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
