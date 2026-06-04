"""
End-to-end runner for the Personify RAG pipeline.

Why this script exists: pytest covers correctness, but to actually *see*
the system in action you want to hand it real documents, ask real
questions, and read the generated essays. That's what this does.

Usage (run from the backend/ directory with venv active):

    cd backend
    source venv/bin/activate
    python ../ai_tests/run_e2e.py

By default it ingests the sample resume + essay in ai_tests/sample_documents/
and asks four representative questions covering all three prompt variants.

To use your own documents, pass them as positional args:

    python ../ai_tests/run_e2e.py /path/to/my_resume.pdf /path/to/my_essay.txt

To ask your own questions, edit the QUESTIONS list below.

What you'll see:
  * Which classification each question got + confidence
  * Which prompt variant fired (motivation / story / background)
  * Which resume chunks were retrieved as context
  * The full generated response

This is the most useful tool for tuning prompts and the confidence
threshold during development.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make `app` and `main` importable when this is run from anywhere.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def _gray(s: str) -> str:
    return f"\033[90m{s}\033[0m"


def _guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".md":
        return "text/markdown"
    return "text/plain"


# Default question set — covers all three prompt variants.
QUESTIONS: list[str] = [
    # motivation variant
    "Why do you want to work at Notion?",
    # story variant
    "Describe a time when you had to make a hard technical tradeoff.",
    # background variant
    "Tell us about yourself and what you care about.",
    # standard field — should be skipped by the pipeline
    "Email address",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end Personify pipeline runner")
    parser.add_argument(
        "documents",
        nargs="*",
        help="Paths to resume/essay files. Defaults to ai_tests/sample_documents/*.",
    )
    parser.add_argument(
        "--company", default="Notion",
        help="Company name injected into the prompt (default: Notion).",
    )
    parser.add_argument(
        "--job-description",
        default="Notion builds tools for thought — collaborative software for "
                "writing, planning, and organizing. We hire engineers who care about "
                "polish, performance, and the feel of products.",
        help="Job description text injected into the prompt.",
    )
    args = parser.parse_args()

    # Import after sys.path setup so the package resolves.
    from app.core.config import settings
    from app.models.schemas import FormField
    from app.services.embeddings import _MEMORY_STORE, ingest_document
    from app.services.pipeline import run_autofill_pipeline

    # Sanity check — without a key the runner technically works but only
    # echoes placeholders. Tell the user clearly.
    if not settings.gemini_api_key:
        print(_yellow("⚠  GEMINI_API_KEY is not set in backend/.env"))
        print(_yellow("   The runner will print placeholder text instead of real"))
        print(_yellow("   generated essays. Set the key and rerun to see actual"))
        print(_yellow("   Gemini output.\n"))

    # Resolve which documents to ingest.
    if args.documents:
        doc_paths = [Path(p).resolve() for p in args.documents]
    else:
        sample_dir = Path(__file__).resolve().parent / "sample_documents"
        doc_paths = sorted(sample_dir.glob("*"))
        if not doc_paths:
            print(_yellow(f"No documents in {sample_dir}; pass paths as args."))
            return 1

    # Clear any prior in-memory state so reruns are deterministic.
    _MEMORY_STORE.clear()

    print(_bold("\n── Ingesting documents ──────────────────────────────"))
    for path in doc_paths:
        if not path.exists():
            print(_yellow(f"  ⚠  Not found: {path}"))
            continue
        content_type = _guess_content_type(path)
        with open(path, "rb") as f:
            summary = ingest_document(
                file_bytes=f.read(),
                content_type=content_type,
                filename=path.name,
                user_id="demo-user",
            )
        print(f"  {_green('✓')} {path.name}  "
              f"chunks={summary['chunks_stored']}  stored_in={summary['stored_in']}")

    # Build FormField objects for the pipeline.
    fields = [
        FormField(selector=f"#q{i}", label=q, field_type="textarea")
        for i, q in enumerate(QUESTIONS, start=1)
    ]

    print(_bold("\n── Running autofill pipeline ────────────────────────"))
    responses = run_autofill_pipeline(
        fields=fields,
        job_description=args.job_description,
        company_name=args.company,
    )
    response_by_selector = {r.selector: r for r in responses}

    print(_bold("\n── Results ──────────────────────────────────────────"))
    for i, q in enumerate(QUESTIONS, start=1):
        selector = f"#q{i}"
        print(_bold(f"\nQ{i}: {q}"))

        if selector not in response_by_selector:
            print(_gray("  → skipped (STANDARD or low confidence)"))
            continue

        resp = response_by_selector[selector]

        # Re-derive the variant the pipeline picked, for visibility.
        from app.services.pipeline import _pick_prompt_variant
        variant, _ = _pick_prompt_variant(q)
        print(_gray(f"  variant: {variant}"))
        print(_green(resp.response))

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())