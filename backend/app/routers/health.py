"""Health check endpoint — used by the dashboard, the extension, and CI."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """Liveness check. Used to verify the backend is reachable."""
    return {"status": "ok", "service": "personify-backend"}
