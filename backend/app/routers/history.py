"""Autofill history endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()
security = HTTPBearer()


class HistoryEntry(BaseModel):
    company_name: str
    question: str
    generated_response: str
    created_at: str


def _supabase():
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_service_key)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        client = _supabase()
        user_response = client.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user_response.user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication error: {str(e)}")


@router.get("", response_model=list[HistoryEntry])
def list_history(user=Depends(get_current_user)):
    try:
        client = _supabase()
        response = (
            client.table("autofill_responses")
            .select("autofill_sessions(company_name), question_text, generated_response, created_at")
            .eq("autofill_sessions.user_id", user.id)
            .order("created_at", desc=True)
            .execute()
        )
        return [
            HistoryEntry(
                company_name=row.get("autofill_sessions", {}).get("company_name", ""),
                question=row.get("question_text", ""),
                generated_response=row.get("generated_response", ""),
                created_at=row.get("created_at", ""),
            )
            for row in (response.data or [])
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
