"""Authentication endpoints. Currently stubbed — to be implemented by Backend Core."""
from fastapi import APIRouter, HTTPException

from app.models.schemas import LoginRequest, SignupRequest, AuthResponse

router = APIRouter()


@router.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest):
    """
    TODO: Wire to Supabase auth.
    - Create user via supabase.auth.sign_up
    - Return session token
    """
    raise HTTPException(status_code=501, detail="signup not yet implemented")


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    """
    TODO: Wire to Supabase auth.
    - Sign in via supabase.auth.sign_in_with_password
    - Return session token
    """
    raise HTTPException(status_code=501, detail="login not yet implemented")
