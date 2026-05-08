"""
Autofill endpoint — the heart of the agent.

Receives field data from the extension content script, runs the
classify → retrieve → generate pipeline, and returns a map of
{ selector → response } that the content script pastes into the page.
"""
from fastapi import APIRouter, Header

from app.models.schemas import AutofillRequest, AutofillResponse, FieldResponse
from app.services.pipeline import DEMO_USER_ID, run_autofill_pipeline

router = APIRouter()


@router.post("", response_model=AutofillResponse)
async def autofill(
    payload: AutofillRequest,
    x_user_id: str | None = Header(default=None),
):
    """
    Run the full agentic autofill pipeline.

    Honors X-User-Id if present (so the extension can identify the user
    once auth is wired); otherwise uses the demo user. Same convention as
    /upload — they need to agree on user_id to share the resume.
    """
    user_id = x_user_id or DEMO_USER_ID

    field_responses: list[FieldResponse] = run_autofill_pipeline(
        fields=payload.fields,
        job_description=payload.job_description,
        company_name=payload.company_name,
        user_id=user_id,
    )

    return AutofillResponse(
        responses=field_responses,
        meta={
            "fields_received": len(payload.fields),
            "fields_filled": len(field_responses),
            "pipeline_version": "0.2-langchain-rag",
            "user_id": user_id,
        },
    )