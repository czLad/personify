# Architectural Decisions

A log of the key technical decisions made during planning, with their reasoning and the alternatives considered. Add to this file as new decisions are made.

---

## ADR-001 — Backend LLM, not extension-side

**Decision:** All LLM calls happen in the FastAPI backend. The extension never holds an API key and never calls Gemini directly.

**Why:**
- The extension is distributed via the Chrome Web Store; embedding API keys is a security violation
- LLM logic can be upgraded server-side without pushing a new extension version
- All sensitive context (user resumes, embeddings) stays server-side

**Alternative considered:** LLM-on-extension via per-user API keys. Rejected — UX is bad (each user has to obtain and paste a key) and it complicates rate limiting.

---

## ADR-002 — Two-step pipeline: classify, then generate

**Decision:** A cheap classification call runs first to identify which fields are personal statements. Only those fields are sent through the expensive generation step.

**Why:**
- Prevents accidentally pasting essays into structured fields like "Years of Experience"
- Reduces cost — 90% of fields on a typical application are STANDARD and don't need generation
- Improves latency — classification is fast (sub-second), generation is the slow step

**Alternative considered:** Single-shot prompt that does both. Rejected — gives the LLM too much rope to hallucinate misclassifications.

---

## ADR-003 — Composite selectors over `id`-only

**Decision:** The content script builds a composite identifier for each field combining `id`, label text, and DOM position rather than relying on `id` alone.

**Why:**
- Workday and Greenhouse use auto-generated, non-stable IDs (e.g., `data-automation-id="wd-TextArea-input-1"`)
- The composite key travels through the full round trip, so the paste step always finds the right field
- Resilient to minor portal UI changes

**Alternative considered:** XPath-based targeting. Rejected — XPaths are even more fragile than composite identifiers when the DOM shifts.

---

## ADR-004 — Supabase over Pinecone + separate DB

**Decision:** Use Supabase for everything: auth, file storage, relational data, and pgvector embeddings.

**Why:**
- Single vendor dramatically reduces infrastructure setup time
- pgvector is mature enough for our scale (likely <100k vectors total during the project)
- Free tier covers our needs

**Alternative considered:** Pinecone (vector) + Postgres (relational) + Firebase (auth). Rejected — three vendors is too much overhead for a 7-week project.

---

## ADR-005 — Hardcoded clicks first, LLM agent layer as stretch

**Decision:** The content script uses deterministic DOM logic for navigation and pasting. The LLM is used only for classification and generation, not for deciding what to click.

**Why:**
- Reliability matters at demo time — agentic browsing can fail unpredictably
- The portals we target have stable enough flows that hardcoded logic works
- The agentic intelligence is in classification + generation (the hard parts), not navigation

**Alternative considered:** Full LLM-driven browser-use agent. Architected as a swappable module for post-MVP iteration but not in scope for the class.

---

## ADR-006 — Vanilla JS in the extension

**Decision:** The Chrome extension is written in vanilla JavaScript with no framework.

**Why:**
- Chrome Manifest V3 only supports plain JS in content scripts; this is a platform constraint, not a preference
- Bundling a framework into a content script bloats injection size unnecessarily
- The extension is intentionally a thin client — no UI logic complex enough to warrant React

**Alternative considered:** None — there isn't one within Manifest V3.

---

## ADR-007 — Python + FastAPI over Node

**Decision:** Backend is Python with FastAPI.

**Why:**
- Python integrates seamlessly with the ML ecosystem we depend on (LangChain, sentence-transformers, embedding libraries)
- FastAPI gives us automatic OpenAPI docs, async support, and Pydantic validation in one
- Team has more Python experience than Node for ML-adjacent work

**Alternative considered:** Node + Express + LangChain.js. Rejected — LangChain.js lags behind the Python version in features and community support.

---

## Adding a new decision

Copy this template and append below:

```
## ADR-NNN — <Title>

**Decision:** ...

**Why:** ...

**Alternative considered:** ...
```
