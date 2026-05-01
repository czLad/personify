# Personify — Architecture

**Course:** CS35L · Spring 2026

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Component Map](#2-component-map)
3. [Workflow 1 — Document Upload & Embedding](#3-workflow-1--document-upload--embedding)
4. [Workflow 2 — Autofill (Core Agentic Loop)](#4-workflow-2--autofill-core-agentic-loop)
5. [Workflow 3 — User Authentication](#5-workflow-3--user-authentication)
6. [Tech Stack Reference](#6-tech-stack-reference)
8. [Key Design Decisions](#8-key-design-decisions)

---

## 1. System Overview

Personify is an **agentic Chrome browser extension** backed by a full-stack web application. The agent follows a **perceive → decide → act** loop autonomously:

- **Perceive** — the content script reads the job application page DOM and collects all form fields with their labels and selectors
- **Decide** — the backend LLM pipeline classifies which fields are personal statement questions, retrieves relevant context from the user's documents via RAG, and generates a personalized response
- **Act** — the content script pastes each generated response into the correct field with no human step in between

The user's role is reduced to two actions: (1) upload documents once via the dashboard, and (2) click "Autofill" on any job application page.

---

## 2. Component Map

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
│  └──────────┬───────────────┘   │  ┌──────────────────────┐  │  │
│             │ HTTPS             │  │  background.js       │  │  │
│             │                   │  │  • Session token     │  │  │
│             │                   │  │  • Message relay     │  │  │
│             │                   │  └──────────────────────┘  │  │
│             │                   └────────────┬───────────────┘  │
└─────────────┼────────────────────────────────┼─────────────────┘
              │ HTTPS                          │ HTTPS
              │                                │
              ▼                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PYTHON BACKEND (FastAPI)                   │
│                                                                 │
│  ┌─────────────────────┐     ┌─────────────────────────────┐   │
│  │  Backend Core       │     │  AI Pipeline                │   │
│  │                     │     │                             │   │
│  │  POST /auth/signup  │     │  POST /autofill             │   │
│  │  POST /auth/login   │     │  POST /embed                │   │
│  │  POST /upload       │     │                             │   │
│  │  GET  /history      │     │  LangChain Pipeline:        │   │
│  │                     │     │  1. Classify fields         │   │
│  └──────────┬──────────┘     │  2. RAG retrieval           │   │
│             │                │  3. Gemini generation       │   │
│             │                └──────────────┬──────────────┘   │
└─────────────┼─────────────────────────────────┼────────────────┘
              │                                 │
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

## 3. Workflow 1 — Document Upload & Embedding

Triggered when the user uploads their resume or essays via the dashboard.

```
User (Dashboard)
      │
      │  1. Selects resume PDF + optional essays
      │
      ▼
Next.js Frontend
      │
      │  2. POST /upload  (multipart/form-data + JWT)
      │
      ▼
FastAPI — /upload endpoint
      │
      │  3. Validates file type and auth token
      │  4. Stores raw file in Supabase Storage
      │
      ▼
AI Pipeline — Embedding step
      │
      │  5. Reads document text
      │  6. Chunks into ~300 token segments
      │  7. Embeds each chunk via sentence-transformers
      │
      ▼
Supabase pgvector
      │
      │  8. Stores (chunk_text, embedding, user_id) rows
      │
      ▼
FastAPI response → Frontend
      │
      │  9. Returns { status: "ok", chunks_stored: N }
      │
      ▼
Dashboard shows confirmation to user
```

**Notes:**
- Chunking strategy: 300 tokens with 50-token overlap to preserve context across boundaries
- Embedding model: `text-embedding-004` (Gemini) or `all-MiniLM-L6-v2` (sentence-transformers) — to be finalized in Week 2
- Re-uploading a document replaces all existing chunks for that user

---

## 4. Workflow 2 — Autofill (Core Agentic Loop)

This is the primary workflow and the heart of the agent. Triggered when the user clicks "Autofill" on a job application page.

```
User clicks "Autofill" in extension popup
      │
      ▼
content_script.js — Perceive
      │
      │  1. Scans DOM for all visible form fields
      │  2. Collects: { label_text, selector, field_type } for each field
      │  3. Scrapes job description text from the page
      │  4. Bundles: { fields[], job_description, company_name }
      │
      ▼
POST /autofill  →  FastAPI
      │
      ├──────────────────────────────────────────────────────────┐
      │                                                          │
      ▼                                                          │
LangChain — Step 1: Field Classification                 │
      │                                                          │
      │  Prompt to Gemini:                                       │
      │  "Classify each field as STANDARD or                     │
      │   PERSONAL_STATEMENT given its label text."              │
      │                                                          │
      │  Returns: { field_id: "STANDARD" | "PERSONAL_STATEMENT" }│
      │                                                          │
      ▼                                                          │
      For each PERSONAL_STATEMENT field:                         │
      │                                                          │
      ▼                                                          │
LangChain — Step 2: RAG Retrieval                        │
      │                                                          │
      │  1. Embeds the question text                             │
      │  2. Queries Supabase pgvector for top-k relevant chunks  │
      │     from this user's resume and essays                   │
      │  3. Returns: [chunk_text_1, chunk_text_2, ...]           │
      │                                                          │
      ▼                                                          │
LangChain — Step 3: Essay Generation                     │
      │                                                          │
      │  Prompt to Gemini:                                       │
      │  - Question: "Why do you want to work at Notion?"        │
      │  - Context chunks: [user's resume/essay excerpts]        │
      │  - Job description: [scraped from page]                  │
      │  - Company: Notion                                       │
      │  - Target: ~100 words, user's preferred tone             │
      │                                                          │
      │  Returns: generated_response (string)                    │
      │                                                          │
      ▼                                                          │
      Repeat for all PERSONAL_STATEMENT fields                   │
      │                                                          │
      └──────────────────────────────────────────────────────────┘
      │
      │  Assembles response map:
      │  { selector: "#field_123", response: "..." }
      │
      ▼
Logs session to Supabase history table
      │
      ▼
FastAPI returns response map to extension
      │
      ▼
content_script.js — Act
      │
      │  For each { selector, response }:
      │    document.querySelector(selector).value = response
      │    dispatches input event to trigger React/Vue watchers
      │
      ▼
Fields are filled. User reviews and submits application.
```

**Notes on selector strategy:**
Not all ATS portals use stable `id` attributes. The content script builds a composite identifier combining: `id` attribute (if unique) + visible label text + DOM position index. This composite key travels with the data through the full round trip to guarantee correct field targeting on messy portals like Workday and Greenhouse.

**Failure handling:**
- If classification returns no PERSONAL_STATEMENT fields → extension shows "No personal statement fields detected"
- If pipeline exceeds 15s → extension shows timeout message, user can retry
- If a selector fails to match on paste → that field is skipped silently, others proceed

---

## 5. Workflow 3 — User Authentication

```
New User                          Returning User
     │                                  │
     │ Fill signup form                 │ Fill login form
     ▼                                  ▼
POST /auth/signup              POST /auth/login
     │                                  │
     │ Supabase creates user            │ Supabase validates credentials
     │                                  │
     ▼                                  ▼
     Returns JWT session token
              │
              ▼
     Stored in chrome.storage.local (extension)
     Stored in localStorage (dashboard)
              │
              ▼
     All subsequent requests include:
     Authorization: Bearer <token>
              │
              ▼
     FastAPI validates token on every
     /upload, /autofill, /history call
```

---

## 6. Tech Stack Reference

| Layer | Technology | Alternative Considered |
|---|---|---| 
| Frontend | Next.js + React | Vue 3 + Nuxt | 
| Backend | Python + FastAPI | Node.js + Express | 
| AI Orchestration | LangChain | LlamaIndex | 
| Vector Store | Supabase pgvector | Pinecone |
| LLM | Gemini API | OpenAI GPT-4o | 
| Chrome Extension | Vanilla JavaScript | N/A |
| Auth + Storage | Supabase | Firebase | 

---

## 7. Key Design Decisions

**Backend LLM, not extension-side LLM**
All LLM logic lives in the FastAPI backend. The extension never holds an API key. This keeps the extension thin, secure, and upgradeable without pushing a new Chrome Web Store release. The extension is purely the eyes and hands — the brain is server-side.

**Two-step pipeline: classify then generate**
Classification runs first as a cheap, fast LLM call. Generation only fires for fields classified as `PERSONAL_STATEMENT`. This prevents the agent from accidentally pasting an essay into a structured field like "Years of Experience."

**Composite selectors over id-only**
Field targeting uses a composite of `id`, label text, and DOM position to handle auto-generated or unstable selectors on Workday and Greenhouse. This is the highest-risk engineering challenge and is being tested in Week 1 before any pipeline code is written

**Supabase over Pinecone + separate DB**
Using Supabase for both the relational data (users, history) and the vector store (pgvector) keeps infrastructure to a single vendor. For a 7-week project, this materially reduces setup complexity and context-switching.

**Hardcoded clicks first, LLM agent as stretch**
The content script uses deterministic DOM logic rather than an LLM deciding what to click. The agent intelligence is in the classification and generation steps, not the navigation. This makes the system reliable at demo time. The fully autonomous navigation layer is architecturally designed as a swappable module for future iterations.
