"""Pydantic schemas shared across routers and services."""
from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    access_token: str


# ── Autofill ──────────────────────────────────────────────────────────────────

class FormField(BaseModel):
    """A single field collected by the content script."""
    selector: str = Field(..., description="Composite selector: id + label + position")
    label: str = Field(..., description="Visible label text near the field")
    field_type: str = Field("text", description="textarea, text, etc.")


class AutofillRequest(BaseModel):
    """What the extension sends when the user clicks Autofill."""
    fields: list[FormField]
    job_description: str = ""
    company_name: str = ""


class FieldResponse(BaseModel):
    """A single generated answer mapped to its field selector."""
    selector: str
    response: str
    classification: str = "PERSONAL_STATEMENT"


class AutofillResponse(BaseModel):
    """What the backend returns to the extension."""
    responses: list[FieldResponse]
    meta: dict
