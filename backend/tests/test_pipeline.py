"""
Skeleton smoke tests + tests for the new AI pipeline behavior.

These tests don't hit the real Gemini API. They verify:
  - The classifier correctly buckets fields.
  - With no API key configured, the pipeline still returns a structured
    response (placeholder text) rather than crashing.
  - The retrieval fallback (in-memory) works end-to-end.
"""
from fastapi.testclient import TestClient

from app.services.embeddings import _MEMORY_STORE, get_memory_store
from app.services.pipeline import DEMO_USER_ID, _quick_classify
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


# ── Classifier ────────────────────────────────────────────────────────────────

def test_quick_classify_personal_statement():
    assert _quick_classify("Why do you want to work at Notion?") == "PERSONAL_STATEMENT"
    assert _quick_classify("Tell us about a challenge you overcame") == "PERSONAL_STATEMENT"
    assert _quick_classify("Cover Letter") == "PERSONAL_STATEMENT"


def test_quick_classify_standard():
    assert _quick_classify("First Name") == "STANDARD"
    assert _quick_classify("LinkedIn URL") == "STANDARD"
    assert _quick_classify("Years of Experience") == "STANDARD"


def test_quick_classify_uncertain():
    assert _quick_classify("Additional Information") is None


# ── Autofill end-to-end ───────────────────────────────────────────────────────

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


# ── Memory store / RAG fallback ───────────────────────────────────────────────

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

    # Confirm the in-memory store now has chunks for the demo user.
    store = get_memory_store()
    assert DEMO_USER_ID in store
    assert len(store[DEMO_USER_ID]) >= 1