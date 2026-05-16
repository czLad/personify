"""
The agentic pipeline.

Step 1 (THIS PR): classify_fields — Gemini decides which fields need
                  a personal statement response.
Step 2 (TODO):    retrieve_context — pgvector returns relevant chunks
                  from the user's uploaded resume/essays.
Step 3 (TODO):    generate_response — Gemini writes a personalized
                  response per field using retrieved context.

The retrieve + generate steps still return stubs so the extension
and frontend contract stays stable.
"""
from __future__ import annotations

import logging

from app.models.schemas import FieldResponse, FormField
from app.services.classifier import classify_fields

logger = logging.getLogger(__name__)


def run_autofill_pipeline(
    fields: list[FormField],
    job_description: str,
    company_name: str,
) -> list[FieldResponse]:
    """
    classify → [retrieve] → [generate]

    Classify step is now live (Gemini via LangChain with heuristic fallback).
    Retrieve + generate are stubs pending pgvector integration.
    """
    if not fields:
        return []

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

    # ── Step 2 & 3: Retrieve + Generate (stubs) ───────────────────────────────
    company = company_name or "this company"
    responses: list[FieldResponse] = []

    for field in fields:
        classification = class_map.get(field.selector, "STANDARD")

        if classification != "PERSONAL_STATEMENT":
            continue

        # TODO(Dev): replace with retrieve_context(field.label, user_id) + generate_response(...)
        stub_response = (
            f"[STUB — classify live, generate pending] "
            f'Personalized answer for "{field.label}" at {company} '
            f"will be generated here once the RAG retrieve+generate steps land."
        )

        responses.append(
            FieldResponse(
                selector=field.selector,
                response=stub_response,
                classification="PERSONAL_STATEMENT",
            )
        )

        logger.debug("Field '%s' classified as PERSONAL_STATEMENT", field.label)

    logger.info(
        "Pipeline complete: %d fields in, %d personal statement fields out",
        len(fields),
        len(responses),
    )

    return responses
