"""Authentication endpoints. Currently stubbed — to be implemented by Backend Core."""
from fastapi import APIRouter, HTTPException

from app.models.schemas import LoginRequest, SignupRequest, AuthResponse, OAuthResponse
from supabase import create_client, Client


router = APIRouter()
SUPABASE_URL = "https://test.supabase.co"
SUPABASE_KEY = "public-anonymous-key"
supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)


@router.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest):
    """
    TODO: Wire to Supabase auth.
    - Create user via supabase.auth.sign_up
    - Return session token
    """
    try:
        response = supabase_client.auth.sign_up({
            "email": payload.email,
            "password": payload.password
        })
        
        # Ensure the response has a session before returning
        if not response.session:
            raise HTTPException(status_code=400, detail="Signup requires email confirmation.")
            
        return AuthResponse(
            user_id=response.user.id,
            access_token=response.session.access_token
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    # raise HTTPException(status_code=501, detail="signup not yet implemented")


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    """
    TODO: Wire to Supabase auth.
    - Sign in via supabase.auth.sign_in_with_password
    - Return session token
    """
    try:
        response = supabase_client.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password
        })

        return AuthResponse(
            user_id=response.user.id,
            access_token=response.session.access_token
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


    # raise HTTPException(status_code=501, detail="login not yet implemented")

@router.post("/login/google", response_model=OAuthResponse)
def login_google():
    """TODO: Implement Google OAuth flow.
    - Generate Google OAuth URL via supabase.auth.sign_in_with_oauth
    - Handle redirect and exchange code for token
    """
    try:
        response = supabase_client.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirectTo": "unknown"
            }
        })
        return OAuthResponse(access_token=response.session.access_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
