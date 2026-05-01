# Roadmap

The skeleton in `main` wires every layer to every other layer with stub responses. From here, each role expands their slice of the system. This file lists what's stubbed and what to build next, organized by role.

---

## Milestone 1 — Working MVP (May 2, 2026)

**Goal:** End-to-end autofill on a real Ashby application page using a real user's uploaded resume.

### Frontend Engineer
- [ ] Real signup / login forms wired to Supabase auth
- [ ] Polished upload UI with drag-and-drop and progress
- [ ] Real history list pulling from `/history`
- [ ] Auth-gated routes — redirect unauthenticated users

### Backend Core Engineer
- [ ] Implement `/auth/signup` and `/auth/login` against Supabase
- [ ] Implement `/upload`: validate file → store in Supabase Storage → enqueue embedding job
- [ ] Implement `/history`: read past sessions from the `autofill_sessions` table
- [ ] JWT auth middleware on all protected routes

### ML Infrastructure Engineer
- [ ] Implement `/embed` service: PDF text extraction, chunking (~300 tokens, 50 overlap), embedding via Gemini
- [ ] Wire pgvector schema and CRUD helpers
- [ ] RAG retrieval helper: `retrieve(question, user_id, k=4)` → list of chunks
- [ ] Health check that includes pgvector connectivity

### Machine Learning Engineer
- [ ] Replace `looks_like_personal_statement` with a real Gemini classification call (LangChain)
- [ ] Build the generation prompt template (question + chunks + JD + company → response)
- [ ] Tune classification prompt to avoid false positives on "Additional Information" fields
- [ ] **Composite selector strategy** in `content_script.js` — combine id, label, DOM position
- [ ] Test detection + paste end-to-end on a real Ashby application

---

## Milestone 2 — Full Feature Set (May 16, 2026)

### Frontend Engineer
- [ ] Settings page wired: tone selector + length selector
- [ ] Edit/delete past history entries

### Backend Core Engineer
- [ ] Persist user preferences (tone, length) and serve them on `/me`
- [ ] Rate limiting on `/autofill` (per user, per minute)

### ML Infrastructure Engineer
- [ ] Cache common company values to reduce Gemini calls
- [ ] Optimize pgvector query with appropriate index (`ivfflat` or `hnsw`)

### Machine Learning Engineer
- [ ] Test selector strategy on Workday and Greenhouse — extend `buildSelector()` per portal
- [ ] Add tone and length to the generation prompt
- [ ] Detect and gracefully skip fields that already have user input

---

## Milestone 3 — Polish & Stretch (June 6, 2026)

### Frontend Engineer
- [ ] Polish for final demo — empty states, animations, dark mode
- [ ] Inline response preview / edit modal in the extension popup (US-09)

### Backend Core Engineer
- [ ] Production logging and error reporting
- [ ] CI: run tests on PRs

### ML Infrastructure Engineer
- [ ] Company value alignment (US-08): fetch or cache company values
- [ ] Latency profiling — bring full pipeline under 10s

### Machine Learning Engineer
- [ ] Stretch: replace deterministic content script logic with an LLM-driven action layer
- [ ] Demo prep: 3-5 reliable test applications across Ashby, Workday, Greenhouse

---

## Branching Convention

`<role-prefix>/<feature>`

- `mle/...` — Machine Learning Engineer
- `mlops/...` — ML Infrastructure Engineer
- `frontend/...` — Frontend Engineer
- `backend/...` — Backend Core Engineer
- `docs/...` — anyone updating documentation
