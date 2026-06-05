"""
Documents listing endpoint.

Powers the dashboard Account page: returns the documents the authenticated
user has uploaded, newest first. Read-only — uploads still go through
POST /upload and the wipe-and-rebuild via DELETE /upload, so this endpoint
always reflects the current stored set without any extra bookkeeping.

Security: the user is identified from the verified Supabase JWT (see
get_current_user), and the query is explicitly scoped to that user's id.
The service-role client bypasses row-level security, so that explicit
.eq("user_id", ...) filter is what enforces per-user isolation here.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.deps import get_current_user, get_supabase

router = APIRouter()


class DocumentItem(BaseModel):
    id: str
    filename: str
    content_type: str | None = None
    # "resume" | "essay" | None. None for rows uploaded before migration 0003
    # (or before the dashboard started stamping the role) — the UI groups
    # those under "Other documents" until they're re-uploaded.
    doc_type: str | None = None
    uploaded_at: str | None = None


@router.get("", response_model=list[DocumentItem])
def list_documents(user=Depends(get_current_user)):
    """Return the current user's uploaded documents, newest first."""
    try:
        client = get_supabase()
        # select("*") rather than naming doc_type so this endpoint also works
        # before migration 0003 is applied (the column simply won't be in the
        # row dicts, and .get() returns None).
        response = (
            client.table("documents")
            .select("*")
            .eq("user_id", user.id)
            .order("uploaded_at", desc=True)
            .execute()
        )
        return [
            DocumentItem(
                id=str(row.get("id", "")),
                filename=row.get("filename", ""),
                content_type=row.get("content_type"),
                doc_type=row.get("doc_type"),
                uploaded_at=row.get("uploaded_at"),
            )
            for row in (response.data or [])
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
