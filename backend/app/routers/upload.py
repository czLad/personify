"""
Document upload endpoint.

Accepts a resume/essay, validates it, then hands it to the embedding
service which chunks + embeds + stores it for later retrieval by the
autofill pipeline.

Auth note: until Yousif wires real auth, uploads use the X-User-Id header
if present, otherwise a single DEMO_USER_ID so the demo works. When auth
lands and X-User-Id is replaced by a verified Supabase auth.users UUID,
the Supabase document_id path in ingest_document activates automatically.
"""
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.embeddings import clear_user_corpus, ingest_document
from app.services.pipeline import DEMO_USER_ID

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"application/pdf", "text/plain", "text/markdown"}
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class UploadResponse(BaseModel):
    status: str
    filename: str
    user_id: str
    chunks_stored: int
    stored_in: str
    # Present only on the supabase path (real auth users). Optional so that
    # the demo response shape doesn't change from today.
    document_id: str | None = None
    doc_type: str | None = None


class ClearResponse(BaseModel):
    status: str
    user_id: str


@router.delete("", response_model=ClearResponse)
async def clear_documents(x_user_id: str | None = Header(default=None)):
    """
    Wipe a user's entire stored corpus (in-memory + Supabase).

    The dashboard calls this once before re-uploading resume + essays, so
    the stored set always matches what's currently attached (wipe-and-
    rebuild). This is why /upload itself stays append-only — the wipe is a
    separate, deliberate action rather than a side effect of uploading.
    """
    user_id = x_user_id or DEMO_USER_ID
    try:
        clear_user_corpus(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clear failed: {e}")
    return ClearResponse(status="cleared", user_id=user_id)


@router.post("", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    x_user_id: str | None = Header(default=None),
    doc_type: str | None = Form(default=None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, TXT, MD",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max is {MAX_FILE_SIZE_MB}MB")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="empty file")

    user_id = x_user_id or DEMO_USER_ID

    try:
        summary = ingest_document(
            file_bytes=contents,
            content_type=file.content_type,
            filename=file.filename,
            user_id=user_id,
            doc_type=doc_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload pipeline failed: {e}")

    return UploadResponse(
        status=summary.get("status", "ok"),
        filename=file.filename,
        user_id=user_id,
        chunks_stored=summary.get("chunks_stored", 0),
        stored_in=summary.get("stored_in", "memory"),
        document_id=summary.get("document_id"),
        doc_type=doc_type,
    )
