"""Document upload endpoint. Stubbed — to be implemented by Backend Core + ML Infra."""
from fastapi import APIRouter, File, UploadFile, HTTPException

router = APIRouter()


@router.post("")
async def upload_document(file: UploadFile = File(...)):
    """
    TODO: Implement full upload pipeline.
    1. Validate file type (PDF, TXT, DOCX)
    2. Store raw file in Supabase Storage
    3. Hand off to embedding service: chunk → embed → store in pgvector
    4. Return chunk count + document ID

    Currently returns a stub response so the frontend can be built against it.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")

    return {
        "status": "stubbed",
        "filename": file.filename,
        "content_type": file.content_type,
        "chunks_stored": 0,
        "note": "real implementation pending — see ROADMAP.md",
    }
