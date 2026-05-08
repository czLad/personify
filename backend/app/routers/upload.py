"""
Document upload endpoint.

For the MVP: accepts a file, hands it to the embedding service which
chunks + embeds + stores it. Yousif will later add Supabase Storage
persistence and tie this to the authenticated user's ID.

Until auth is wired, all uploads go to a single DEMO_USER_ID so the
demo works.
"""
from fastapi import APIRouter, File, Header, HTTPException, UploadFile

from app.services.embeddings import ingest_document
from app.services.pipeline import DEMO_USER_ID

router = APIRouter()


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    x_user_id: str | None = Header(default=None),
):
    """
    Upload a resume or essay, chunk it, embed each chunk, and store the
    embeddings for later retrieval by the autofill pipeline.

    The X-User-Id header is honored if present (so Yousif's auth middleware
    can pass through a real user_id once it's wired). Otherwise we use the
    demo user.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="empty file")

    user_id = x_user_id or DEMO_USER_ID

    summary = ingest_document(
        file_bytes=contents,
        content_type=file.content_type,
        filename=file.filename,
        user_id=user_id,
    )

    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "user_id": user_id,
        **summary,
    }