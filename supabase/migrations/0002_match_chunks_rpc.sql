-- Personify migration 0002: pgvector retrieval RPC
-- Run this in the Supabase SQL editor AFTER 0001_initial.sql.
--
-- This creates the function that retrieval.py calls to find the top-k
-- most semantically similar chunks for a given query embedding.

create or replace function match_document_chunks(
  query_embedding vector(768),
  match_user_id   uuid,
  match_count     int default 3
)
returns table (
  id          uuid,
  content     text,
  similarity  float
)
language plpgsql
as $$
begin
  return query
  select
    document_chunks.id,
    document_chunks.content,
    1 - (document_chunks.embedding <=> query_embedding) as similarity
  from document_chunks
  where document_chunks.user_id = match_user_id
    and document_chunks.embedding is not null
  order by document_chunks.embedding <=> query_embedding
  limit match_count;
end;
$$;