"""Autofill history endpoint. Stubbed — to be implemented by Backend Core."""
from fastapi import APIRouter, HTTPException

router = APIRouter()
# Can be replaced with data from .env.example?
SUPABASE_URL = "https://test.supabase.co"
SUPABASE_KEY = "public-anonymous-key"
supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Used to extract the Bearer token from the Authorization header
security = HTTPBearer()

class HistoryEntry(BaseModel):
    company_name: str
    question: str
    generated_response: str
    created_at: str

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validates the user's access token with Supabase and returns the user object."""
    token = credentials.credentials
    try:
        user_response = supabase_client.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user_response.user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication error: {str(e)}")

@router.get("", response_model=list[HistoryEntry])
def list_history():
    """
    TODO: Return autofill history for the authenticated user.
    Each entry: { company_name, question, generated_response, created_at }.
    """

    # Need to access SQL table "autofill_history" filtered by user_id, ordered by created_at desc
    try:
        # Placeholder for actual database query
        response = (supabase_client.table("autofill_history")
            .select("company_name, question, generated_response, created_at")
            .eq("user_id", get_current_user().id)
            .order("created_at", desc=True)
            .execute()
        )

        return response.data  # Assuming response.data is a list of dicts matching HistoryEntry
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Then make returned entries match the above format

    # return {
    #     "status": "stubbed",
    #     "items": [],
    #     "note": "real implementation pending — see ROADMAP.md",
    # }
