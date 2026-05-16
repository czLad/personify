"""
/classify endpoint — standalone field classification.

Lets the extension (or tests) call classification independently
from the full autofill pipeline. Useful for debugging and for
future UX where the extension previews which fields it will fill
before the user clicks Autofill.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.classifier import classify_fields, FieldClassification

router = APIRouter()


class ClassifyRequest(BaseModel):
    fields: list[dict]  # [{selector, label, field_type}]


class ClassifyResponse(BaseModel):
    classifications: list[FieldClassification]
    classifier_used: str  # "llm" or "heuristic_fallback"


@router.post("", response_model=ClassifyResponse)
async def classify(payload: ClassifyRequest):
    """
    Classify form fields as PERSONAL_STATEMENT or STANDARD.

    The service tries Gemini first and falls back to a keyword
    heuristic if the LLM call fails. The classifier_used field
    in the response tells you which path was taken.
    """
    results = classify_fields(payload.fields)

    # Detect fallback: heuristic results all have confidence=0.6
    used_heuristic = all(r.confidence == 0.6 for r in results) and len(results) > 0

    return ClassifyResponse(
        classifications=results,
        classifier_used="heuristic_fallback" if used_heuristic else "llm",
    )
