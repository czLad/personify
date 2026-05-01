# Personify — Architecture

## System Overview

Personify is an **agentic Chrome browser extension** backed by a full-stack web application. The agent follows a **perceive → decide → act** loop autonomously:

- **Perceive** — the content script reads the job application page DOM and collects all form fields with their labels and selectors
- **Decide** — the backend LLM pipeline classifies which fields are personal statement questions, retrieves relevant context from the user's documents via RAG, and generates a personalized response
- **Act** — the content script pastes each generated response into the correct field with no human step in between

The user's role is reduced to two actions: (1) upload documents once via the dashboard, and (2) click "Autofill" on any job application page.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER'S BROWSER                           │
│                                                                 │
│  ┌──────────────────────────┐   ┌────────────────────────────┐  │
│  │   Next.js Dashboard      │   │   Chrome Extension         │  │
│  │   (Frontend)             │   │                            │  │
│  │                          │   │  ┌──────────────────────┐  │  │
│  │  • Upload resume/essays  │   │  │  content_script.js   │  │  │
│  │  • View autofill history │   │  │  • Scans DOM         │  │  │
│  │  • Configure settings    │   │  │  • Sends fields      │  │  │
│  │                          │   │  │  • Pastes responses  │  │  │
│  └──────────┬───────────────┘   │  └──────────────────────┘  │  │
│             │ HTTPS             │  ┌──────────────────────┐  │  │
│             │                   │  │  background.js       │  │  │
│             │                   │  │  • Session token     │  │  │
│             │                   │  │  • Message relay     │  │  │
│             │                   │  └──────────────────────┘  │  │
│             │                   └────────────┬───────────────┘  │
└─────────────┼────────────────────────────────┼─────────────────┘
              │ HTTPS                          │ HTTPS
              ▼                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PYTHON BACKEND (FastAPI)                   │
│                                                                 │
│  ┌─────────────────────┐     ┌─────────────────────────────┐    │
│  │  Backend Core       │     │  AI Pipeline                │    │
│  │                     │     │                             │    │
│  │  POST /auth/signup  │     │  POST /autofill             │    │
│  │  POST /auth/login   │     │  POST /embed                │    │
│  │  POST /upload       │     │                             │    │
│  │  GET  /history      │     │  LangChain Pipeline:        │    │
│  │                     │     │  1. Classify fields         │    │
│  └──────────┬──────────┘     │  2. RAG retrieval           │    │
│             │                │  3. Gemini generation       │    │
│             │                └──────────────┬──────────────┘    │
└─────────────┼─────────────────────────────────┼────────────────-┘
              ▼                                 ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│        Supabase             │   │       Gemini API            │
│                             │   │                             │
│  • User auth                │   │  • Field classification     │
│  • Document storage         │   │  • Essay generation         │
│  • pgvector embeddings      │   │                             │
│  • Autofill history log     │   │                             │
└─────────────────────────────┘   └─────────────────────────────┘
```

---

## Workflow 1 — Document Upload & Embedding

```
User (Dashboard)
      │  1. Selects resume PDF + optional essays
      ▼
Next.js Frontend
      │  2. POST /upload  (multipart/form-data + JWT)
      ▼
FastAPI — /upload endpoint
      │  3. Validates file type and auth token
      │  4. Stores raw file in Supabase Storage
      ▼
AI Pipeline — Embedding step
      │  5. Reads document text
      │  6. Chunks into ~300 token segments
      │  7. Embeds each chunk via Gemini embeddings
      ▼
Supabase pgvector
      │  8. Stores (chunk_text, embedding, user_id) rows
      ▼
FastAPI response → Frontend confirmation
```

**Notes**
- Chunking: ~300 tokens with 50-token overlap
- Re-uploading replaces all existing chunks for that user

---

## Workflow 2 — Autofill (the agentic loop)

```
User clicks "Autofill" in extension popup
      ▼
content_script.js — PERCEIVE
      │  1. Scans DOM for all visible form fields
      │  2. Collects { label, selector, field_type } for each
      │  3. Scrapes job description text from the page
      │  4. POST /autofill { fields, job_description, company }
      ▼
LangChain — Step 1: Classify
      │  Gemini classifies each field as STANDARD or PERSONAL_STATEMENT
      ▼
For each PERSONAL_STATEMENT field:
      ▼
LangChain — Step 2: Retrieve
      │  Embed the question text → query pgvector → top-k relevant chunks
      ▼
LangChain — Step 3: Generate
      │  Gemini writes a ~100 word response using:
      │    - the question
      │    - retrieved chunks from user's resume/essays
      │    - the scraped job description
      │    - company name + values
      ▼
Backend assembles { selector → response } map
      │
      ▼
content_script.js — ACT
      │  For each entry:
      │    document.querySelector(selector).value = response
      │    dispatch input + change events for React/Vue compatibility
      ▼
Form is filled. User reviews and submits.
```

**Selector strategy** — Workday and Greenhouse use auto-generated, unstable selectors. Targeting combines `id` + label text + DOM position into a composite key that travels through the full round trip.

**Failure modes**
- No PERSONAL_STATEMENT fields detected → extension shows "no personal statement fields found"
- Pipeline timeout (>15s) → extension shows retry option
- Selector fails to match on paste → that field is skipped silently

---

## Workflow 3 — Authentication

```
New user                          Returning user
  │ Fill signup form                │ Fill login form
  ▼                                 ▼
POST /auth/signup           POST /auth/login
  │ Supabase creates user           │ Supabase validates
  ▼                                 ▼
        Returns JWT session token
              │
              ▼
   chrome.storage.local (extension)
   localStorage (dashboard)
              │
              ▼
   All subsequent requests:
   Authorization: Bearer <token>
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js + React |
| Backend | Python + FastAPI |
| AI Orchestration | LangChain |
| Vector Store | Supabase pgvector |
| LLM | Gemini API |
| Chrome Extension | Vanilla JavaScript (Manifest V3) |
| Auth + Storage | Supabase |

For comparison with alternatives, see [`DECISIONS.md`](DECISIONS.md).
