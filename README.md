# Personify

> **Agentic AI for job application personal statements.**

Personify is an agentic Chrome browser extension backed by a full-stack web application that automates the personal statement portion of job applications. Users upload their resume and past essays once via the dashboard; clicking "Autofill" on any job application page detects open-ended questions like *"Why do you want to work here?"* and generates a personalized, context-aware response — pasted automatically into the correct field.

Unlike Simplify, which only autofills structured fields and skips personal statement questions entirely, Personify fills exactly that gap using a RAG-powered LLM pipeline.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Running the Project Locally](#running-the-project-locally)
- [Workflow](#workflow)
- [Architectural Decisions](#architectural-decisions)
- [Project Status](#project-status)
- [Contributing](#contributing)

---

## Features

**Implemented:**
- Document upload pipeline: extract → chunk → embed → store (Supabase pgvector, with an in-memory fallback when Supabase isn't configured)
- LangChain classify → retrieve → generate flow with Gemini (2.5-flash chat + gemini-embedding-001)
- Confidence-gated autofill — generation only fires for fields the classifier is sure about
- Retrieval quality layers: query boost (company + job description folded into the embedding query) and cross-question MMR diversity
- Three prompt variants (motivation / story / background) routed by question shape
- Supabase auth end-to-end: JWT sessions, `X-User-Id` on upload and autofill, per-user document isolation
- Dashboard upload with staged files and wipe-and-rebuild semantics (re-uploads never duplicate chunks)
- Chrome extension content script + smoke-test harness (`ai_tests/fake_job_page.html`)

**Remaining (stretch / hardening):**
- ⏳ Composite selector hardening for messy ATS portals (Workday, Greenhouse)
- ⏳ Production-quality error handling and logging

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what each role owns next.

---

## Architecture

The system follows a **perceive → decide → act** agentic loop:

```
┌──────────────────────────────────────────────────────────────┐
│                      USER'S BROWSER                          │
│  ┌──────────────────────┐    ┌────────────────────────────┐  │
│  │   Next.js Dashboard  │    │   Chrome Extension         │  │
│  │   (upload, history)  │    │   content_script + popup   │  │
│  └──────────┬───────────┘    └────────────┬───────────────┘  │
└─────────────┼─────────────────────────────┼──────────────────┘
              │ HTTPS                       │ HTTPS
              ▼                             ▼
┌──────────────────────────────────────────────────────────────┐
│                  PYTHON BACKEND (FastAPI)                    │
│  ┌──────────────────┐         ┌───────────────────────────┐  │
│  │  Backend Core    │         │  AI Pipeline              │  │
│  │  /auth /upload   │         │  /autofill /classify      │  │
│  │  /documents      │         │  LangChain pipeline       │  │
│  │  /history        │         │  (RAG + prompt variants)  │  │
│  └────────┬─────────┘         └─────────────┬─────────────┘  │
└───────────┼─────────────────────────────────┼────────────────┘
            ▼                                 ▼
   ┌────────────────────┐         ┌────────────────────────┐
   │     Supabase       │         │      Gemini API        │
   │  auth + pgvector   │         │ classify · embed · gen │
   └────────────────────┘         └────────────────────────┘
```

For the full architecture including detailed workflow diagrams, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Repository Structure

```
personify/
├── backend/                  Python FastAPI service
│   ├── app/
│   │   ├── core/             Config, settings, Supabase client
│   │   ├── routers/          /auth, /upload, /documents, /autofill, /history
│   │   ├── services/         LangChain pipeline, embeddings, retrieval
│   │   └── models/           Pydantic schemas
│   ├── tests/
│   ├── requirements.txt
│   └── main.py
│
├── frontend/                 Next.js + React dashboard
│   ├── src/
│   │   ├── app/              App router pages (upload, history, settings)
│   │   ├── components/       Shared UI components
│   │   └── lib/              API client, types
│   └── package.json
│
├── extension/                Chrome extension (Manifest V3)
│   ├── src/
│   │   ├── content_script.js Scans DOM, sends fields, pastes responses
│   │   ├── background.js     Service worker, session management
│   │   └── popup.html        Extension popup UI
│   ├── icons/
│   └── manifest.json
│
├── ai_tests/                 Smoke-test harness + e2e CLI runner
├── docs/                     Architecture, roadmap, decisions
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── DECISIONS.md
│   └── INTERFACE_SPEC.md
│
├── supabase/                 SQL migrations and pgvector setup
│   └── migrations/
│
├── .github/workflows/        CI for lint and build
└── README.md
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | Next.js + React | Strong ecosystem, team has React experience |
| Backend | Python + FastAPI | Integrates seamlessly with ML libraries; agile development |
| AI Orchestration | LangChain | Mature RAG abstractions for the classify-retrieve-generate pipeline |
| Vector Store | Supabase pgvector | Combined relational DB and vector search in one service |
| LLM | Gemini API | Generous free tier — decisive for a no-budget class project |
| Chrome Extension | Vanilla JavaScript | Manifest V3 only supports plain JS in content scripts |
| Auth + Storage | Supabase | Already chosen for pgvector; consolidates auth and storage |

---

## Getting Started

### Prerequisites

- **Node.js** 20+ and **npm**
- **Python** 3.11+
- **Supabase** account (free tier works)
- **Google Gemini API key** (free tier works)
- **Google Chrome** for testing the extension

### Clone and install

```bash
git clone https://github.com/<your-org>/personify.git
cd personify

# Backend
cd backend
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env         # then fill in keys

# Frontend
cd ../frontend
npm install
cp .env.local.example .env.local

# Extension — no install needed; loaded as unpacked extension
```

### Configure Supabase

1. Create a new Supabase project at [supabase.com](https://supabase.com)
2. In the SQL editor, run the migrations in `supabase/migrations/` in order
3. Copy the project URL, anon key, and **service_role key** into `backend/.env` (the service key is what lets the backend write embeddings)

---

## Running the Project Locally

Open three terminal tabs:

**Terminal 1 — Backend**
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend**
```bash
cd frontend
npm run dev
```

**Terminal 3 — Extension**
1. Open Chrome → `chrome://extensions`
2. Toggle **Developer mode** on (top right)
3. Click **Load unpacked** → select the `extension/` directory
4. Pin the extension to your toolbar

**Verify the stack is wired:**
- Visit `http://localhost:8000/health` — should return `{ "status": "ok" }`
- Visit `http://localhost:3000` — Next.js dashboard loads
- Click the extension icon → popup loads → click "Test connection" → reaches the backend

---

## Workflow

### How Personify works — RAG + Autofill

```text
┌─────────────────────────────  USER'S BROWSER  ─────────────────────────────┐
│                                                                            │
│   ┌──────────────────────────┐          ┌──────────────────────────────┐   │
│   │    Next.js Dashboard     │          │       Chrome Extension       │   │
│   │  login · attach + upload │          │  content_script: scans form, │   │
│   │  resume + essays         │          │  detects open-ended fields,  │   │
│   │                          │          │  pastes generated answers    │   │
│   └────────────┬─────────────┘          └───────────────┬──────────────┘   │
└────────────────┼────────────────────────────────────────┼──────────────────┘
                 │ (A) POST /upload                        │ (B) POST /autofill
                 │     X-User-Id + file                    │     X-User-Id + fields
                 ▼                                         ▼     + job description
┌────────────────────────────────────────────────────────────────────────────┐
│                               FASTAPI BACKEND                              │
│                                                                            │
│    UPLOAD PIPELINE — per file           AUTOFILL PIPELINE — per question   │
│   ┌──────────────────────────┐          ┌──────────────────────────────┐   │
│   │ extract text + normalize │          │ 1 classify the field         │   │
│   │ chunk (800 chars,        │          │   confidence < 0.7 → skip    │   │
│   │        100 overlap)      │          │ 2 retrieve top-k chunks      │   │
│   │ embed each chunk         │          │   query boost · MMR penalty  │   │
│   │ store under user_id      │          │ 3 generate the answer        │   │
│   └────────────┬─────────────┘          │   prompt variant by question │   │
│                │                        └───────────────┬──────────────┘   │
└────────────────┼────────────────────────────────────────┼──────────────────┘
                 │ insert chunks                ┌──────────┤
                 │ + embeddings                 │ per-user │ embed · classify
                 ▼                              ▼ search   ▼ · generate
   ┌──────────────────────────────────────────────┐  ┌─────────────────────────┐
   │          SUPABASE — auth + pgvector          │  │        GEMINI API       │
   │   auth.users · documents · document_chunks   │  │ gemini-2.5-flash (chat) │
   │               (vector(768))                  │  │ gemini-embedding-001    │
   └──────────────────────────────────────────────┘  └─────────────────────────┘

   (B) returns [{ selector, response }] → the extension pastes each answer
       into its matching field
```

The autofill pipeline (B) is the RAG core: each answer is generated only from
the user's own resume/essay chunks, retrieved per question with a boosted
query and an MMR diversity penalty, so every field stays grounded in the
applicant's real experience.

### The autofill loop in detail

1. User clicks **Autofill** in the extension popup on any job application page
2. `content_script.js` scans the DOM, collecting every form field with its label and selector
3. Bundled fields + scraped job description are POSTed to `/autofill` with the user's `X-User-Id`
4. Backend pipeline runs three steps via LangChain:
   - **Classify** — Gemini decides which fields are personal statements (a confidence threshold skips uncertain fields)
   - **Retrieve** — pgvector returns the most relevant chunks from the user's resume and essays (the query is boosted with the company name and job description)
   - **Generate** — Gemini writes a personalized response per field using a prompt variant matched to the question type
5. Backend returns a list of `{ selector, response }` pairs plus request metadata
6. Content script pastes each response into the correct field

### Document upload (separate workflow)

1. User attaches resume/essays via the dashboard and clicks **Upload documents**
2. Backend clears the user's previous corpus, then for each file: extracts text, splits it into 800-character chunks (100 overlap), embeds each chunk with Gemini, and stores everything in Supabase pgvector tied to the user's ID (in-memory fallback when Supabase isn't configured)

For sequence diagrams, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Architectural Decisions

The shorthand list — full reasoning is in [`docs/DECISIONS.md`](docs/DECISIONS.md).

- **Backend LLM, not extension-side LLM.** The extension never holds an API key. All intelligence is server-side; the extension is just eyes and hands.
- **Two-step pipeline: classify, then generate.** A cheap classification call runs first; expensive generation only fires for fields confirmed as personal statements. Prevents accidental essay injection into structured fields.
- **Composite selectors over `id`-only.** Workday and Greenhouse use auto-generated, unstable selectors. Targeting combines `id`, label text, and DOM position for resilience.
- **Supabase over Pinecone + separate DB.** One vendor for relational data, vector search, auth, and file storage. Reduces infrastructure complexity.
- **Hardcoded clicks first, fully autonomous LLM agent as stretch.** Reliable demo behavior comes from deterministic content-script logic. The agent intelligence lives in classification and generation, not navigation.
- **Vanilla JS in the extension.** Not a preference — a Manifest V3 platform constraint.

---

## Project Status

All core functionality is implemented and working end-to-end: document upload with Supabase pgvector storage, the classify → retrieve → generate pipeline against the real Gemini API, per-user auth, and autofill through both the smoke-test harness and the extension. Remaining work is hardening (ATS portal selectors, production error handling) per the [roadmap](docs/ROADMAP.md).

**Milestone schedule:**
- **Milestone 1 — Working MVP** — May 9, 2026 ✅
- **Milestone 2 — Full Feature Set** — May 16, 2026 ✅
- **Milestone 3 — Polish & Stretch** — June 6, 2026

---

## Contributing

This is a class project for CS35L at UCLA. For internal team conventions:

- Branch naming: `<role-prefix>/<feature>` — e.g. `mle/classify-prompt`, `frontend/upload-page`, `backend/auth`, `mlops/embed-endpoint`
- Open a PR against `main` and request review from at least one teammate
- Run linters before pushing: `npm run lint` (frontend, extension), `ruff check` (backend)
- Update the relevant doc in `docs/` if your change affects architecture or workflow