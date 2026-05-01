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

**Implemented in this skeleton:**
- Project structure for all four components (extension, frontend, backend, AI pipeline)
- Health check endpoints between every layer
- Stub `/autofill` endpoint that returns mock generated responses
- Chrome extension scaffold with a content script that talks to the backend
- Next.js dashboard scaffold with one upload page and one history page
- Supabase + pgvector schema migrations
- Environment variable templates

**To be implemented (assigned across the team):**
- ⏳ Real document upload, chunking, and embedding pipeline
- ⏳ LangChain classify → retrieve → generate flow
- ⏳ Gemini API integration
- ⏳ Composite selector strategy for messy ATS portals
- ⏳ Authentication flow end-to-end
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
│  │  /auth /upload   │         │  /autofill /embed         │  │
│  │  /history        │         │  LangChain pipeline       │  │
│  └────────┬─────────┘         └─────────────┬─────────────┘  │
└───────────┼─────────────────────────────────┼────────────────┘
            ▼                                 ▼
   ┌────────────────────┐         ┌────────────────────┐
   │     Supabase       │         │    Gemini API      │
   │  auth + pgvector   │         │  classify + gen    │
   └────────────────────┘         └────────────────────┘
```

For the full architecture including detailed workflow diagrams, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Repository Structure

```
personify/
├── backend/                  Python FastAPI service
│   ├── app/
│   │   ├── core/             Config, settings, Supabase client
│   │   ├── routers/          /auth, /upload, /autofill, /history
│   │   ├── services/         LangChain pipeline, embeddings
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
├── docs/                     Architecture, roadmap, decisions
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   └── DECISIONS.md
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
3. Copy the project URL and anon key into both `.env` files

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

The core agentic flow is the **autofill loop**:

1. User clicks **Autofill** in the extension popup on any job application page
2. `content_script.js` scans the DOM, collecting every form field with its label and selector
3. Bundled fields + scraped job description are POSTed to `/autofill`
4. Backend pipeline runs three steps via LangChain:
   - **Classify** — Gemini decides which fields are personal statements
   - **Retrieve** — pgvector returns the most relevant chunks from the user's resume
   - **Generate** — Gemini writes a personalized response per field
5. Backend returns a map of `{ selector → response }`
6. Content script pastes each response into the correct field

Document upload (separate workflow):
1. User uploads resume/essays via the dashboard
2. Backend chunks the document into ~300 token segments
3. Each chunk is embedded and stored in Supabase pgvector tied to the user's ID

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

This repository currently contains the **skeleton only**. Every layer has just enough code to communicate with the next layer for a health check. Real functionality is implemented incrementally per the [roadmap](docs/ROADMAP.md).

**Milestone schedule:**
- **Milestone 1 — Working MVP** — May 2, 2026
- **Milestone 2 — Full Feature Set** — May 16, 2026
- **Milestone 3 — Polish & Stretch** — June 6, 2026

---

## Contributing

This is a class project for CS35L at UCLA. For internal team conventions:

- Branch naming: `<role-prefix>/<feature>` — e.g. `mle/classify-prompt`, `frontend/upload-page`, `backend/auth`, `mlops/embed-endpoint`
- Open a PR against `main` and request review from at least one teammate
- Run linters before pushing: `npm run lint` (frontend, extension), `ruff check` (backend)
- Update the relevant doc in `docs/` if your change affects architecture or workflow
