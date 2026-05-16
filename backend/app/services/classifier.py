"""
Field classification service.

Exposes two implementations:
  - heuristic_classify   : fast keyword fallback (no LLM call)
  - llm_classify         : Gemini-powered classifier via LangChain

The pipeline uses llm_classify by default and falls back to
heuristic_classify if the LLM call fails or times out.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

FieldClass = Literal["PERSONAL_STATEMENT", "STANDARD"]

# ── Heuristic fallback ────────────────────────────────────────────────────────

_PS_KEYWORDS = (
    "why",
    "tell us",
    "describe",
    "what motivates",
    "interest",
    "challenge",
    "background",
    "experience",
    "passion",
    "goal",
    "strength",
    "weakness",
    "about yourself",
    "contribution",
    "diverse",
    "unique",
)

_STANDARD_KEYWORDS = (
    "name",
    "email",
    "phone",
    "address",
    "gpa",
    "graduation",
    "linkedin",
    "github",
    "website",
    "portfolio",
    "salary",
    "start date",
    "zip",
    "city",
    "state",
    "country",
)


def heuristic_classify(label: str) -> FieldClass:
    """
    Keyword-based classifier. O(1), no network call.
    Used as fallback when LLM is unavailable.
    """
    lower = label.lower()
    if any(k in lower for k in _STANDARD_KEYWORDS):
        return "STANDARD"
    if any(k in lower for k in _PS_KEYWORDS):
        return "PERSONAL_STATEMENT"
    # Default: if the field is a textarea it's probably open-ended
    return "STANDARD"


# ── LLM classifier ────────────────────────────────────────────────────────────

class FieldClassification(BaseModel):
    selector: str
    classification: FieldClass
    confidence: float  # 0.0–1.0, informational only


_SYSTEM_PROMPT = """\
You are a form field classifier for a job application autofill tool.

Your job: given a list of form field labels from a job application page,
classify each as either PERSONAL_STATEMENT or STANDARD.

PERSONAL_STATEMENT: open-ended questions that require a personalized written
response. Examples: "Why do you want to work here?", "Tell us about a
challenge you overcame", "Describe your experience with machine learning".

STANDARD: structured fields with a specific expected format. Examples:
name, email, phone, GPA, graduation date, LinkedIn URL, years of experience
(numeric), salary expectation, city/state, pronouns, work authorization.

Rules:
- When in doubt, prefer STANDARD to avoid over-filling.
- A field with a word limit or "in X words" hint is almost always PERSONAL_STATEMENT.
- Short factual fields are STANDARD even if phrased as questions.

Respond ONLY with a JSON array. No markdown, no explanation.
Each element: {"selector": "<selector>", "classification": "PERSONAL_STATEMENT"|"STANDARD", "confidence": 0.0-1.0}
"""


def llm_classify(
    fields: list[dict],  # list of {selector, label, field_type}
    *,
    timeout: float = 8.0,
) -> list[FieldClassification]:
    """
    Classify fields using Gemini. Returns a FieldClassification per field.
    Raises on network/parse failure — caller should catch and fall back.
    """
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=settings.gemini_api_key,
        timeout=timeout,
        temperature=0,
    )

    field_lines = "\n".join(
        f'- selector="{f["selector"]}" label="{f["label"]}" type="{f.get("field_type", "text")}"'
        for f in fields
    )

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"Classify these form fields:\n{field_lines}"),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    parsed = json.loads(raw)
    return [FieldClassification(**item) for item in parsed]


# ── Public interface ──────────────────────────────────────────────────────────

def classify_fields(
    fields: list[dict],
) -> list[FieldClassification]:
    """
    Classify fields with LLM, falling back to heuristic on failure.
    This is the function the pipeline should call.
    """
    if not fields:
        return []

    try:
        results = llm_classify(fields)
        logger.info("LLM classifier succeeded for %d fields", len(fields))
        return results
    except Exception as exc:
        logger.warning(
            "LLM classifier failed (%s), falling back to heuristic", exc
        )
        return [
            FieldClassification(
                selector=f["selector"],
                classification=heuristic_classify(f["label"]),
                confidence=0.6,
            )
            for f in fields
        ]
