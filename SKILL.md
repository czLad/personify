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

Multi-file + multi-user semantics (Supabase path):
- Uploads **append**, they don't wipe the user. So resume + essays
  uploaded as separate calls both persist. (`save_chunks_pgvector` is
  append-only.)
- Re-uploading the **same filename** replaces just that document:
  `_insert_documents_row` deletes the prior `(user_id, filename)` row
  first, and the `document_chunks ... on delete cascade` FK removes its
  old chunks. A differently-named file is untouched. So editing
  resume.pdf and re-uploading replaces the resume without duplicating
  and without touching essays.pdf.
- Isolation is by `user_id` — the retrieval RPC filters
  `where user_id = …`, so teammates must each use their **own** account
  (own signup → own UUID). Sharing one account mixes and clobbers data.
  Use `retrieval.clear_user_chunks_pgvector(user_id)` for an explicit
  wipe (parity with the in-memory `clear_user_chunks`).

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

### 8. Retrieval uses a boosted query (Week 7)
`retrieve()` does NOT just embed the bare question. The query string fed
to `embed_query` is the question concatenated with the company name and
a truncated job description (see `retrieval._build_query`). Why: resumes
describe outputs ("Built X using Y") while essays describe decisions
("I chose A over B"), so on technical questions essay chunks naturally
win on semantic similarity. The boost adds role-specific vocabulary to
the query so resume chunks compete on their actual content.

Two knobs to know:
* `pipeline.RETRIEVAL_K` (default 4) — how many chunks per question.
* `retrieval._JOB_DESCRIPTION_BUDGET` (default 200) — how many chars of
  the job description get folded in before truncation. The question
  must stay the dominant signal in the embedding.

If you change either, also re-tune the other. Larger k with a larger
budget = more diverse but more diluted context. Tests for both live in
`test_pipeline.py::TestQueryBoost` and `::TestBuildQuery`.

### 9. Retrieval applies cross-question MMR (Week 7)
On a single autofill batch, the same chunk (or another chunk from the
same experience) tends to win for multiple questions — Q1 and Q2 both
get the NASA story, Q3 too. We adapt **Maximum Marginal Relevance**
(Carbonell & Goldstein, 1998) across questions: chunks already used in
this batch are penalized when scoring candidates for later ones.

Implementation: `pipeline.run_autofill_pipeline` keeps a `used_embeddings`
list across its field loop and passes it as `penalize` to each `retrieve()`
call. `retrieval._retrieve_memory_mmr` subtracts
`penalty_weight · max_sim(candidate, penalize)` from each candidate's
query similarity before ranking. See module docstring of `retrieval.py`
for the formula and its relationship to classical MMR's λ.

Two knobs:
* `pipeline.MMR_PENALTY_WEIGHT` (default 0.4) — diversity bias. Plays
  the role of `(1 − λ)` in classical MMR. Higher → stronger diversity;
  0 → off (pure relevance).
* `pipeline.GENERATION_TEMPERATURE` (default 0.65) — tuned through
  several iterations. 0.7 ignored structural rules; 0.5 followed them
  but produced staccato prose with no narrative connective tissue;
  0.65 strikes a balance. If essays drift back toward generic
  promotional language, drop to 0.6 before going lower.

Important: the **pgvector path does NOT apply MMR yet** (the current
SQL RPC doesn't return embeddings). When promoting pgvector, see the
commented-out `_retrieve_pgvector_mmr` sketch in `retrieval.py` for the
migration path. The in-memory demo path is fully MMR-enabled.

Tests live in `test_pipeline.py::TestMMRDeduplicationPipeline` (plumbing)
and `::TestMMRScoring` (math).

### 10. Prompt templates are hard-ruled (Week 7)
Each variant template in `pipeline.py` enforces several rules in
`_BASE_INSTRUCTIONS`:
* **Persona**: opens with "you are a thoughtful applicant writing in
  your own voice." Frames the LLM as a person speaking, not a marketing
  copywriter. Added after the first prompt rewrite produced staccato
  bullet-style essays.
* **Concrete-detail requirement**: every response must reference ≥2
  specific items from the resume excerpts (project name, technology,
  place, number, named experience). Kills generic-glue filler like
  "I'm passionate about optimal algorithm design."
* **Sentence-rhythm rule**: most sentences between 8 and 25 words. Bans
  both run-on compound sentences (the pre-Week-7 failure mode) and
  choppy 5-word fragments (the over-correction). Aims for a rhythm a
  recruiter could read aloud.
* **Subtle-alignment + no-cliché-closer guard**: blocklist on glue
  phrases ("aligns with", "I'm drawn to") AND on promotional closers
  ("I am eager to contribute", "impactful software that ships"). Ban
  on verbatim quoting of the job description. The model otherwise
  substitutes one cliché for another.
* **Aspiration guard**: phrasings like "I would like to" or "I hope to"
  in the corpus are NOT to be claimed as completed experiences. This
  prevents leakage from aspirational essay content (e.g. "I would like
  to engage with PAC at Stanford" being reported as actual work).

Variant-specific (length ranges chosen to fit the shape of each
question type; explicit anti-padding instruction in each template):
* `motivation`: 110–150 words, target ~130, single paragraph. Shows a
  concrete detail first; the body draws an **explicit bridge** from
  that experience to a value, technical direction, or product theme
  stated in the job description (without quoting it verbatim and
  without naming the company). The company name appears only in the
  final sentence, at most. This is the variant where the
  applicant→company alignment has to be made legible; the other two
  variants stay focused on the applicant.
* `story`: 150–210 words, target ~180, one or two paragraphs. Opens
  with scene-setting (project, role, stakes) for 1–2 sentences, then
  decision → result → learning. Does NOT name the company.
* `background`: 130–180 words, target ~150, one or two paragraphs.
  Opens with a moment/person/experience, ends on a forward-looking
  note. Does NOT name the company.

Paragraph breaks: a single break is permitted in any variant when the
response has two distinct beats (past → present, decision → reflection,
etc.). Stay in one paragraph otherwise. No headings, no bullet points.

If you tweak these, also bump `GENERATION_TEMPERATURE` if needed. The
LLM ignores structural rules at higher temperatures and produces
staccato prose at lower ones.

### 11. PDF text gets normalized at ingestion (Week 7 fix)
`embeddings.extract_text` collapses runs of whitespace into single
spaces before returning. PyPDF2 on LaTeX-generated PDFs (like Min's
resume) can return text with every word on its own line, which made
both retrieval logs unreadable and the chunks Gemini saw look bizarre.
The chunker still splits cleanly via its sentence/word fallback
separators. If you ever need paragraph-aware chunking back, this is
the place to revisit — keep `\n\n` paragraph breaks and only normalize
intra-paragraph whitespace.

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
- Week 7: Query boost (company + job description folded into the
  embedding query) ✓ — see `retrieval._build_query`. Cross-question MMR
  diversity ✓ — see `retrieval._retrieve_memory_mmr` and the
  `MMR_PENALTY_WEIGHT` constant. Prompt rewrite for show-then-state,
  short sentences, subtle alignment, and concrete-detail requirement ✓
  — see `pipeline._BASE_INSTRUCTIONS` and the three variant templates.
  INFO-level logging enabled at app startup ✓ (`main.py`) plus per-field
  prompt logging in `pipeline._generate_response`.