"""
Document embedding service.

Takes a raw uploaded file, chunks it into passages, embeds each chunk
using Gemini text-embedding-004, and stores the results in Supabase:
  - documents table       : one row per file
  - document_chunks table : one row per chunk, with 768-dim embedding
"""
from __future__ import annotations

import logging
import uuid
from io import BytesIO

import PyPDF2
from google.generativeai import embed_content
import google.generativeai as genai
from supabase import create_client, Client

from app.core.config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "models/text-embedding-004"
EMBEDDING_DIMS = 768


def _get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


def extract_text(file_bytes: bytes, content_type: str) -> str:
    if content_type == "application/pdf":
        reader = PyPDF2.PdfReader(BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n".join(pages)
    if content_type in ("text/plain", "text/markdown"):
        return file_bytes.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported content type: {content_type}")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_size - overlap
    return chunks


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    genai.configure(api_key=settings.gemini_api_key)
    embeddings = []
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        result = embed_content(
            model=EMBEDDING_MODEL,
            content=batch,
            task_type="retrieval_document",
        )
        embeddings.extend(result["embedding"])
    return embeddings


def store_document_and_chunks(
    user_id: str,
    filename: str,
    content_type: str,
    storage_path: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> tuple[str, int]:
    supabase = _get_supabase()
    document_id = str(uuid.uuid4())
    supabase.table("documents").insert({
        "id": document_id,
        "user_id": user_id,
        "filename": filename,
        "content_type": content_type,
        "storage_path": storage_path,
    }).execute()
    chunk_rows = [
        {
            "document_id": document_id,
            "user_id": user_id,
            "chunk_index": idx,
            "content": chunk,
            "embedding": embedding,
        }
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    batch_size = 50
    for i in range(0, len(chunk_rows), batch_size):
        supabase.table("document_chunks").insert(chunk_rows[i : i + batch_size]).execute()
    logger.info("Stored document %s with %d chunks for user %s", document_id, len(chunks), user_id)
    return document_id, len(chunks)


def process_upload(
    user_id: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> tuple[str, int]:
    logger.info("Processing upload: %s (%s) for user %s", filename, content_type, user_id)
    text = extract_text(file_bytes, content_type)
    if not text.strip():
        raise ValueError("No text could be extracted from the uploaded file.")
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("Document produced no chunks after extraction.")
    logger.info("Extracted %d chunks from %s", len(chunks), filename)
    embeddings = embed_chunks(chunks)
    storage_path = f"uploads/{user_id}/{filename}"
    document_id, chunks_stored = store_document_and_chunks(
        user_id=user_id,
        filename=filename,
        content_type=content_type,
        storage_path=storage_path,
        chunks=chunks,
        embeddings=embeddings,
    )
    return document_id, chunks_stored
