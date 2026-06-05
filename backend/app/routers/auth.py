"""Authentication endpoints — wired to Supabase Auth."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.deps import get_current_user
from app.models.schemas import AuthResponse, LoginRequest, SignupRequest

router = APIRouter()


class MeResponse(BaseModel):
    user_id: str
    email: str | None = None


def _supabase():
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@router.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest):
    """Create a new user via Supabase Auth."""
    try:
        client = _supabase()
        res = client.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
        })
        if not res.user or not res.session:
            raise HTTPException(status_code=400, detail="Signup failed — check email/password")
        return AuthResponse(
            user_id=res.user.id,
            access_token=res.session.access_token,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    """Sign in an existing user via Supabase Auth."""
    try:
        client = _supabase()
        res = client.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password,
        })
        if not res.user or not res.session:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        return AuthResponse(
            user_id=res.user.id,
            access_token=res.session.access_token,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=MeResponse)
def me(user=Depends(get_current_user)):
    """Return basic profile info for the authenticated user."""
    return MeResponse(user_id=user.id, email=getattr(user, "email", None))
