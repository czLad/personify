"""
Document upload endpoint.
"""
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.services.embedder import process_upload

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
}

MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class UploadResponse(BaseModel):
    status: str
    document_id: str
    filename: str
    chunks_stored: int


def _get_user_id(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        import base64, json
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("no sub claim")
        return user_id
    except Exception:
        raise HTTPException(status_code=401, detail="Could not parse user ID from token")


@router.post("", response_model=UploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
):
    user_id = _get_user_id(request)
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, TXT, MD",
        )
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB")
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        document_id, chunks_stored = process_upload(
            user_id=user_id,
            filename=file.filename or "unnamed",
            content_type=file.content_type,
            file_bytes=file_bytes,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload pipeline failed: {e}")
    return UploadResponse(
        status="ok",
        document_id=document_id,
        filename=file.filename or "unnamed",
        chunks_stored=chunks_stored,
    )
