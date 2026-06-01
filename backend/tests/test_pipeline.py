"""
Tests for the pipeline orchestration and the /autofill HTTP endpoint.

These tests don't hit the real Gemini API. Classification is mocked out
(it has its own test file). The pipeline tests focus on:

  - HTTP endpoint wiring (/health, /autofill, /upload)
  - Pipeline correctly skips STANDARD fields
  - user_id threading + DEMO_USER_ID fallback
  - Graceful handling when GEMINI_API_KEY is absent
  - End-to-end memory store population from /upload
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models.schemas import FormField
from app.services.classifier import FieldClassification
from app.services.embeddings import _MEMORY_STORE, get_memory_store
from app.services.pipeline import DEMO_USER_ID, run_autofill_pipeline
from main import app

client = TestClient(app)


# ── Health / wiring ───────────────────────────────────────────────────────────

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root():
    r = client.get("/")
    assert r.status_code == 200


# ── /autofill HTTP endpoint (no Gemini key needed — placeholder text is fine) ─

def test_autofill_skips_standard_fields():
    """STANDARD fields should not get a generated response."""
    r = client.post("/autofill", json={
        "fields": [
            {"selector": "#name", "label": "First Name", "field_type": "text"},
            {"selector": "#email", "label": "Email Address", "field_type": "text"},
        ],
        "job_description": "",
        "company_name": "Acme",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["responses"]) == 0
    assert body["meta"]["fields_received"] == 2
    assert body["meta"]["fields_filled"] == 0


def test_autofill_targets_personal_statement_fields():
    """PERSONAL_STATEMENT fields should get a response (placeholder if no API key)."""
    r = client.post("/autofill", json={
        "fields": [
            {"selector": "#why", "label": "Why do you want to work at Notion?", "field_type": "textarea"},
            {"selector": "#name", "label": "First Name", "field_type": "text"},
        ],
        "job_description": "Building tools for thought.",
        "company_name": "Notion",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["responses"]) == 1
    assert body["responses"][0]["selector"] == "#why"
    assert body["responses"][0]["classification"] == "PERSONAL_STATEMENT"
    assert isinstance(body["responses"][0]["response"], str)
    assert len(body["responses"][0]["response"]) > 0


# ── Pipeline function directly (classification mocked) ────────────────────────

@patch("app.services.pipeline.classify_fields")
def test_pipeline_empty_fields_short_circuits(mock_classify):
    """No fields in → no classifier call, no responses out."""
    result = run_autofill_pipeline([], "", "")
    assert result == []
    mock_classify.assert_not_called()


@patch("app.services.pipeline.classify_fields")
def test_pipeline_uses_demo_user_when_no_user_id(mock_classify):
    """If caller doesn't pass user_id, DEMO_USER_ID is used downstream."""
    mock_classify.return_value = [
        FieldClassification(selector="#q1", classification="PERSONAL_STATEMENT", confidence=0.9),
    ]
    fields = [FormField(selector="#q1", label="Why?", field_type="textarea")]

    with patch("app.services.pipeline.retrieve") as mock_retrieve:
        mock_retrieve.return_value = []
        run_autofill_pipeline(fields, "", "Notion")
        # Confirm retrieve was called with the demo user, not None
        mock_retrieve.assert_called_once()
        assert mock_retrieve.call_args.kwargs["user_id"] == DEMO_USER_ID


@patch("app.services.pipeline.classify_fields")
def test_pipeline_passes_through_explicit_user_id(mock_classify):
    """If caller passes user_id, it's threaded all the way to retrieve."""
    mock_classify.return_value = [
        FieldClassification(selector="#q1", classification="PERSONAL_STATEMENT", confidence=0.9),
    ]
    fields = [FormField(selector="#q1", label="Why?", field_type="textarea")]

    with patch("app.services.pipeline.retrieve") as mock_retrieve:
        mock_retrieve.return_value = []
        run_autofill_pipeline(fields, "", "Notion", user_id="user-123")
        assert mock_retrieve.call_args.kwargs["user_id"] == "user-123"


# ── /upload → memory store integration ───────────────────────────────────────

def test_memory_store_is_populated_after_upload():
    """Uploading a text file should populate the in-memory chunk store."""
    _MEMORY_STORE.clear()

    sample_resume = (
        "Min Phone Myat Zaw — UCLA Computer Science, expected 2027.\n\n"
        "Experience: built a Chrome extension that uses a LangChain pipeline "
        "to fill personal statement questions on job applications.\n\n"
        "Skills: Python, JavaScript, FastAPI, React, LangChain, RAG."
    ).encode("utf-8")

    r = client.post(
        "/upload",
        files={"file": ("resume.txt", sample_resume, "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["chunks_stored"] >= 1

    store = get_memory_store()
    assert DEMO_USER_ID in store
    assert len(store[DEMO_USER_ID]) >= 1
    
# ── /upload validation ────────────────────────────────────────────────────────

def test_upload_rejects_unsupported_type():
    """An unsupported MIME type should return 415."""
    r = client.post(
        "/upload",
        files={"file": ("resume.docx", b"fake docx bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert r.status_code == 415
    assert "Unsupported file type" in r.json()["detail"]


def test_upload_rejects_empty_file():
    """An empty file should return 400."""
    r = client.post(
        "/upload",
        files={"file": ("resume.txt", b"", "text/plain")},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_upload_rejects_oversized_file():
    """A file over 10MB should return 413."""
    huge = b"x" * (11 * 1024 * 1024)  # 11MB
    r = client.post(
        "/upload",
        files={"file": ("resume.txt", huge, "text/plain")},
    )
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


def test_upload_accepts_markdown():
    """The allowlist includes text/markdown; should succeed."""
    md_resume = b"# Min\n\nUCLA CS, building Personify."
    r = client.post(
        "/upload",
        files={"file": ("resume.md", md_resume, "text/markdown")},
    )
    assert r.status_code == 200
    assert r.json()["chunks_stored"] >= 1