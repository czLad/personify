# SKILL.md — Working on Personify

This file teaches a future Claude (or any agent) how to be productive
in this codebase quickly. It encodes the conventions, gotchas, and the
team context that aren't obvious from reading the code alone.

## What this project is

Personify is a CS35L Spring 2026 group project at UCLA. It's an agentic
Chrome extension that auto-fills personal-statement questions on job
applications. The backend uses LangChain + RAG over the user's uploaded
resume/essays, calling Gemini for both classification and generation.

Team:
- **Min Phone Myat Zaw (GitHub: czLad)** — MLE / AI infra (you usually
  work with him). Owns embeddings, retrieval, the prompt pipeline.
- **Dev Raja (GitHub: devraja37)** — backend/ML infra. Owns the field
  classifier service, eventually Supabase wiring.
- **Yousif Alkhalaf** — backend core. Owns auth (Supabase auth) and the
  HTTP routers. Auth is not landed yet.
- **Daphne Nea** — frontend. Owns the Next.js dashboard.

## Repo shape

```
backend/                  FastAPI app
  app/
    core/config.py         env-loaded Pydantic settings
    models/schemas.py      Pydantic request/response shapes
    routers/               one file per endpoint
    services/
      classifier.py        Dev — Gemini classifier + heuristic fallback
      embeddings.py        Min — extract + chunk + embed + store
      pipeline.py          Min — classify → retrieve → generate
      retrieval.py         Min — pgvector + in-memory fallback
  tests/
    test_classifier.py     Dev
    test_pipeline.py       pipeline + /autofill
    test_upload.py         /upload + document_id wiring
    test_embeddings.py     pure-function unit tests
  pyproject.toml           ruff config
  requirements.txt         pinned exactly (Lecture 12 reuse rules)

frontend/                 Next.js 15 dashboard (App Router)
extension/                Chrome MV3 extension (vanilla JS)
supabase/migrations/      pgvector schema (not yet deployed)
docs/INTERFACE_SPEC.md    /autofill contract
ai_tests/run_e2e.py       CLI runner — feed real docs, see real output
.github/workflows/ci.yml  pytest + ruff + frontend build
```

## Critical conventions

### 1. Two storage paths exist; pick the right one automatically
`embeddings.ingest_document` chooses between:
- **memory** (default, demo path): Supabase not configured OR write failed.
- **pgvector**: Supabase configured + user_id is a string. Chunks only.
- **supabase**: Supabase configured + user_id is a real UUID. Inserts a
  `documents` row AND chunks linked by `document_id`.

The UUID detection (`_looks_like_uuid`) is the gate. Demo flows pass
`"demo-user"` (not a UUID) so they never accidentally write to the
`documents` table — that's good, because the FK requires `auth.users(id)`.

### 2. Inline imports are intentional
Heavy libs (`google.generativeai`, `PyPDF2`, `supabase`) are imported
**inside functions** so:
- Tests that mock these paths don't pay the import cost.
- The `/health` endpoint loads instantly.
- Circular imports between `embeddings.py` and `retrieval.py` are broken
  by lazy `from app.services.retrieval import save_chunks_pgvector`.

Don't "fix" this by moving imports to the top of the file.

### 3. Confidence threshold gates expensive work
`pipeline.MIN_CONFIDENCE = 0.7`. Heuristic-fallback classifications come
back at `confidence=0.6` deliberately so they're filtered out when the
LLM is unavailable. This is the "don't paste an essay into an ambiguous
field" promise from the Week 4 weekly report.

If you raise this, also re-tune the heuristic confidence. If you lower
it, you'll start auto-filling fields the classifier wasn't sure about.

### 4. Prompt variants live in `pipeline.py`
`_pick_prompt_variant(question)` returns `(variant_name, template)`.
Three variants:
- `motivation` — for "why ..." / "interested in" questions
- `story` — for "describe a time" / "tell us about a time" prompts
- `background` — everything else

The selection is regex-based, deterministic, and testable without the LLM.
When adding a new variant, also add a test in
`tests/test_pipeline.py::TestPromptVariantSelection`.

### 5. The /autofill contract is documented and stable
See `docs/INTERFACE_SPEC.md`. The extension and frontend depend on this
shape. If you change the response shape, bump `meta.pipeline_version`
and coordinate with whoever owns the extension.

Hidden internals (LLM choice, prompt variant chosen, retrieval mode) are
**not** exposed in the response by design — this is the narrow-interface
principle from the Week 5 weekly report.

### 6. Real Gemini calls in tests
The CI runs three tests against the real Gemini API: anything that goes
through `/upload` end-to-end or `/autofill` end-to-end without mocking
`embeddings.embed_*` or `pipeline.classify_fields`. These need a real
`GEMINI_API_KEY` GitHub secret. If you add more such tests, be aware
they'll consume real quota on every PR push.

For pure logic tests, mock `app.services.pipeline.classify_fields` and
`app.services.pipeline.retrieve` (see `test_pipeline.py` for patterns).

### 7. Gemini model names matter
We currently use:
- `gemini-2.5-flash` for chat (in `.env`)
- `models/gemini-embedding-001` (hardcoded in `embeddings.py`)
- `output_dimensionality=768` to match the pgvector schema (`vector(768)`)

If you change the embedding model, also update the migration's
`vector(N)` size.

## Common tasks

### Run the test suite locally
```bash
cd backend
source venv/bin/activate
pytest -v
```

You'll see warnings about `gotrue` deprecation — harmless, it's Supabase's
internal package.

### See real Gemini output for your own resume
```bash
cd backend
source venv/bin/activate
python ../ai_tests/run_e2e.py /path/to/your_resume.pdf
```

Edit the `QUESTIONS` list in `ai_tests/run_e2e.py` to test specific prompts.

### Add a new classifier keyword
Edit `app/services/classifier.py`'s `_PS_KEYWORDS` or `_STANDARD_KEYWORDS`
tuples. Add a test case in `tests/test_classifier.py::TestHeuristicClassify`.

### Add a new prompt variant
1. Add a new constant `_MY_VARIANT_TEMPLATE` in `pipeline.py`. Include all
   four placeholders: `{company} {job_description} {context} {question}`.
2. Add a regex to detect the cue.
3. Add a branch in `_pick_prompt_variant`.
4. Add a test in `TestPromptVariantSelection`.

### Modify the response shape
1. Update `models/schemas.py`.
2. Bump `meta.pipeline_version` in `routers/autofill.py`.
3. Update `docs/INTERFACE_SPEC.md`.
4. Tell Daphne and whoever owns the extension.

## Gotchas

- **Don't reuse old Gemini API keys.** One was committed to `.env.example`
  early in the project and had to be rotated. New keys go in `.env` only,
  which is gitignored.
- **Don't `git pull origin main` while on a feature branch unless you
  intend to merge main INTO that branch.** Use `git merge origin/main`
  for clarity.
- **`requirements.txt` is pinned for a reason.** Don't loosen pins. If
  you need a newer version of something, update the pin explicitly.
- **The `EMBEDDING_DIM` constant in `embeddings.py` is locked at 768**
  to match the pgvector column. Changing it requires a migration.
- **`stored_in` in the upload response can be `"memory"`, `"pgvector"`,
  or `"supabase"`.** The frontend should not assume any particular value
  is "the production path" — it should only care that `chunks_stored > 0`.
- **Test isolation:** `_MEMORY_STORE` is module-level state. Tests that
  exercise `/upload` should `_MEMORY_STORE.clear()` first.

## Weekly report style

If you're asked to draft a weekly project report, the user's voice is:
- Short, plain English, 2–3 sentences per question.
- No bullet points.
- Casual but technical.
- Q1 = "what I did this week", Q2 = "how I applied a lecture concept".
- Reference specific files / decisions / lecture concepts where natural.

Don't promise things that aren't in the codebase. If a report promises
something, the codebase needs to back it up — that's why this file's
"What's promised" history matters.

## Promises log (things the codebase MUST contain)

- Week 3: LangChain + RAG pipeline, in-memory fallback ✓
- Week 4: Confidence threshold ✓, prompt variations ✓, pinned deps ✓
- Week 5: Code review pass ✓, end-to-end real-Gemini test ✓
- Week 6: Interface spec in repo ✓ (`docs/INTERFACE_SPEC.md`)