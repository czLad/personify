"""
Autofill endpoint — the heart of the agent.

Receives field data from the extension content script, runs the
classify → retrieve → generate pipeline, and returns a map of
{ selector → response } that the content script pastes into the page.
"""
from fastapi import APIRouter

from app.models.schemas import AutofillRequest, AutofillResponse, FieldResponse
from app.services.pipeline import run_autofill_pipeline

router = APIRouter()


@router.post("", response_model=AutofillResponse)
async def autofill(payload: AutofillRequest):
    """
    Run the full agentic autofill pipeline.

    Currently returns a deterministic mock so the extension and frontend
    can be wired end-to-end before the real LangChain pipeline lands.
    """
    field_responses: list[FieldResponse] = run_autofill_pipeline(
        fields=payload.fields,
        job_description=payload.job_description,
        company_name=payload.company_name,
    )

    return AutofillResponse(
        responses=field_responses,
        meta={
            "fields_received": len(payload.fields),
            "fields_filled": len(field_responses),
            "pipeline_version": "stub-0.1",
        },
    )
