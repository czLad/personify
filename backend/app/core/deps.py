"""
Shared FastAPI dependencies.

`get_current_user` verifies the Supabase access token sent as a Bearer
header and returns the authenticated Supabase user (which carries both
`.id` and `.email`). This is the secure way to identify the caller —
unlike the X-User-Id header the upload path trusts for the demo, the JWT
is validated by Supabase, so a client can't claim to be another user.
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

security = HTTPBearer()


def get_supabase():
    """Lazy import + construct so missing creds don't break module import."""
    if not (settings.supabase_url and settings.supabase_service_key):
        raise HTTPException(status_code=503, detail="Supabase not configured")
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_service_key)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        client = get_supabase()
        user_response = client.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user_response.user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication error: {e}")