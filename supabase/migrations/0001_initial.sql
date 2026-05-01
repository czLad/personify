-- Personify initial schema
-- Run this in the Supabase SQL editor.

-- Enable pgvector
create extension if not exists vector;

-- ── Documents ──────────────────────────────────────────────────────────────
-- Stores raw uploaded documents per user.
create table if not exists documents (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  filename        text not null,
  content_type    text,
  storage_path    text not null,
  uploaded_at     timestamptz not null default now()
);

create index if not exists idx_documents_user on documents(user_id);

-- ── Document chunks ────────────────────────────────────────────────────────
-- Each chunk has its embedding for RAG retrieval.
-- Using 768 dims for Gemini's text-embedding-004; adjust if model changes.
create table if not exists document_chunks (
  id              uuid primary key default gen_random_uuid(),
  document_id     uuid not null references documents(id) on delete cascade,
  user_id         uuid not null references auth.users(id) on delete cascade,
  chunk_index     int not null,
  content         text not null,
  embedding       vector(768),
  created_at      timestamptz not null default now()
);

create index if not exists idx_chunks_user on document_chunks(user_id);
create index if not exists idx_chunks_embedding on document_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- ── Autofill sessions ──────────────────────────────────────────────────────
-- One row per Autofill button click.
create table if not exists autofill_sessions (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  company_name    text,
  page_url        text,
  fields_detected int not null default 0,
  fields_filled   int not null default 0,
  created_at      timestamptz not null default now()
);

create index if not exists idx_sessions_user_created on autofill_sessions(user_id, created_at desc);

-- ── Autofill responses ─────────────────────────────────────────────────────
-- One row per generated response within a session (for history + review).
create table if not exists autofill_responses (
  id                  uuid primary key default gen_random_uuid(),
  session_id          uuid not null references autofill_sessions(id) on delete cascade,
  question_text       text not null,
  generated_response  text not null,
  edited_response     text,
  created_at          timestamptz not null default now()
);

create index if not exists idx_responses_session on autofill_responses(session_id);

-- ── User preferences ───────────────────────────────────────────────────────
create table if not exists user_preferences (
  user_id         uuid primary key references auth.users(id) on delete cascade,
  tone            text default 'balanced',     -- formal | balanced | conversational
  target_words    int  default 100,            -- 50 | 100 | 150
  updated_at      timestamptz not null default now()
);

-- ── Row level security ─────────────────────────────────────────────────────
alter table documents          enable row level security;
alter table document_chunks    enable row level security;
alter table autofill_sessions  enable row level security;
alter table autofill_responses enable row level security;
alter table user_preferences   enable row level security;

create policy "users can read their own docs"
  on documents for select using (auth.uid() = user_id);
create policy "users can insert their own docs"
  on documents for insert with check (auth.uid() = user_id);
create policy "users can delete their own docs"
  on documents for delete using (auth.uid() = user_id);

create policy "users can read their own chunks"
  on document_chunks for select using (auth.uid() = user_id);
create policy "users can insert their own chunks"
  on document_chunks for insert with check (auth.uid() = user_id);

create policy "users can read their own sessions"
  on autofill_sessions for select using (auth.uid() = user_id);
create policy "users can insert their own sessions"
  on autofill_sessions for insert with check (auth.uid() = user_id);

create policy "users can read their own responses"
  on autofill_responses for select using (
    exists (select 1 from autofill_sessions s where s.id = session_id and s.user_id = auth.uid())
  );

create policy "users can read their own prefs"
  on user_preferences for select using (auth.uid() = user_id);
create policy "users can upsert their own prefs"
  on user_preferences for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
