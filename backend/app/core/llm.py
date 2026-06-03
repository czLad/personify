"""
Single source of truth for the chat LLM client.

Centralized here so that:

  * The model name lives in exactly one place — driven by
    settings.gemini_model from .env. When Google deprecates a model
    (see the gemini-1.5-flash → 2.5 churn), we change the .env and
    every caller picks it up.

  * Temperature can differ per use case (deterministic for classifier,
    higher for generation) without each caller importing
    ChatGoogleGenerativeAI directly.

  * The lazy-import pattern is consistent: heavy LangChain deps don't
    load until we actually need them.

Callers should NOT import ChatGoogleGenerativeAI directly anywhere else
in the codebase. If you find yourself wanting to, add a new helper
function here instead.
"""
from __future__ import annotations

from app.core.config import settings


def get_chat_llm(*, temperature: float, timeout: float | None = None):
    """
    Build a ChatGoogleGenerativeAI configured from settings.

    Returns None if no API key is set — callers should treat this as
    "Gemini is unavailable" and degrade gracefully (placeholder text,
    heuristic fallback, etc).

    Args:
        temperature: 0.0 for deterministic tasks (classification, parsing),
                     0.7+ for creative generation.
        timeout:     per-request timeout in seconds. None means LangChain's
                     default. Pass a short value (e.g. 8s) for interactive
                     paths where a slow API is worse than a fallback.
    """
    if not settings.gemini_api_key:
        return None

    # Lazy: langchain_google_genai pulls a lot in. Skip if no key.
    from langchain_google_genai import ChatGoogleGenerativeAI

    kwargs: dict = {
        "model": settings.gemini_model,
        "google_api_key": settings.gemini_api_key,
        "temperature": temperature,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout

    return ChatGoogleGenerativeAI(**kwargs)
