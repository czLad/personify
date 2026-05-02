"""Autofill history endpoint. Stubbed — to be implemented by Backend Core."""
from fastapi import APIRouter

router = APIRouter()


@router.get("")
def list_history():
    """
    TODO: Return autofill history for the authenticated user.
    Each entry: { company_name, question, generated_response, created_at }.
    """
    return {
        "status": "stubbed",
        "items": [],
        "note": "real implementation pending — see ROADMAP.md",
    }
