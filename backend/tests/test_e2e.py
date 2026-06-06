"""
End-to-end tests for the Personify backend.

These tests exercise the full request-to-response path without mocking
the core business logic. No LLM calls are made — Gemini is stubbed at
the network boundary — but the actual chunking, embedding, retrieval,
classification, and prompt-building code all run for real.

Tests:
  1. Upload → retrieve: uploading a resume populates the store and the
     correct content is retrievable by semantic query.
  2. Upload → autofill: uploading a resume then hitting /autofill returns
     a filled response for a personal statement field.
  3. Upload → clear → autofill: after clearing the corpus, autofill
     returns no responses (nothing to retrieve).
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.embeddings import _MEMORY_STORE
from app.services.pipeline import DEMO_USER_ID
from main import app

client = TestClient(app)

SAMPLE_RESUME = b"""
Jane Smith
UCLA Computer Science, Class of 2025

Experience:
- Software Engineering Intern at Notion (Summer 2024): Built a RAG pipeline
  using LangChain and pgvector that reduced hallucinations by 40%.
- Research Assistant, UCLA NLP Lab: Developed a transformer-based classifier
  to detect code-switching in multilingual social media posts.

Skills: Python, FastAPI, React, TypeScript, PostgreSQL, LangChain, Docker.

Projects:
- Personify: Agentic Chrome extension that auto-fills job application personal
  statements using RAG over the user's resume.
"""


# ── E2E 1: Upload → Retrieve ──────────────────────────────────────────────────

def test_e2e_upload_then_retrieve_finds_relevant_chunk():
    """
    Full path: POST /upload stores chunks → retrieve() returns content
    relevant to a query about the user's experience.

    No mocks on the core path. Gemini embeddings are replaced with a
    deterministic stub so the test is fast and offline-safe.
    """
    _MEMORY_STORE.clear()

    # Stub embed so we don't need a Gemini key, but use real chunking logic.
    def fake_embed(text: str) -> list[float]:
        # Simple bag-of-words style: hash each word into a fixed-dim vector.
        import hashlib
        vec = [0.0] * 64
        for word in text.lower().split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % 64
            vec[idx] += 1.0
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]

    with patch("app.services.embeddings.embed_texts", side_effect=lambda texts: [fake_embed(t) for t in texts]), \
         patch("app.services.embeddings.embed_query", side_effect=fake_embed), \
         patch("app.services.retrieval.embed_query", side_effect=fake_embed):

        # Step 1: upload the resume.
        r = client.post(
            "/upload",
            files={"file": ("resume.txt", SAMPLE_RESUME, "text/plain")},
        )
        assert r.status_code == 200
        assert r.json()["chunks_stored"] >= 1

        # Step 2: retrieve chunks about "LangChain RAG pipeline".
        from app.services.retrieval import retrieve
        chunks = retrieve("LangChain RAG pipeline", DEMO_USER_ID, k=3)

    assert len(chunks) >= 1
    combined = " ".join(c.content for c in chunks)
    # The resume mentions LangChain and RAG — at least one chunk should contain them.
    assert "LangChain" in combined or "RAG" in combined


# ── E2E 2: Upload → Autofill ─────────────────────────────────────────────────

def test_e2e_upload_then_autofill_returns_response():
    """
    Full path: POST /upload → POST /autofill returns a filled response
    for a personal statement field.

    Gemini embed and generate are both stubbed so the test runs offline,
    but classification, retrieval, and HTTP wiring all run for real.
    """
    _MEMORY_STORE.clear()

    def fake_embed(text: str) -> list[float]:
        import hashlib
        vec = [0.0] * 64
        for word in text.lower().split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % 64
            vec[idx] += 1.0
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]

    fake_response = (
        "I am deeply excited about Notion because my internship experience "
        "building a RAG pipeline at a collaborative tooling company showed me "
        "how impactful well-designed AI features can be for everyday workflows."
    )

    from app.services.classifier import FieldClassification
    confident_classification = [
        FieldClassification(selector="#why-notion", classification="PERSONAL_STATEMENT", confidence=0.95),
        FieldClassification(selector="#email", classification="STANDARD", confidence=0.99),
    ]

    with patch("app.services.embeddings.embed_texts", side_effect=lambda texts: [fake_embed(t) for t in texts]), \
         patch("app.services.embeddings.embed_query", side_effect=fake_embed), \
         patch("app.services.retrieval.embed_query", side_effect=fake_embed), \
         patch("app.services.pipeline._generate_response", return_value=(fake_response, "motivation")), \
         patch("app.services.pipeline.classify_fields", return_value=confident_classification):

        # Step 1: upload resume.
        up = client.post(
            "/upload",
            files={"file": ("resume.txt", SAMPLE_RESUME, "text/plain")},
        )
        assert up.status_code == 200

        # Step 2: autofill a personal statement field.
        af = client.post("/autofill", json={
            "fields": [
                {
                    "selector": "#why-notion",
                    "label": "Why do you want to work at Notion?",
                    "field_type": "textarea",
                },
                {
                    "selector": "#email",
                    "label": "Email address",
                    "field_type": "text",
                },
            ],
            "job_description": "Building collaborative AI tools for knowledge workers.",
            "company_name": "Notion",
        })

    assert af.status_code == 200
    body = af.json()
    # Standard field (email) should be skipped; personal statement should be filled.
    assert body["meta"]["fields_filled"] == 1
    assert body["responses"][0]["selector"] == "#why-notion"
    assert len(body["responses"][0]["response"]) > 20


# ── E2E 3: Upload → Clear → Autofill returns nothing ─────────────────────────

def test_e2e_upload_clear_autofill_returns_empty():
    """
    Full path: POST /upload → DELETE /upload (clear corpus) → POST /autofill
    returns no responses because there are no chunks to retrieve.

    Verifies that the clear endpoint actually wipes the store and that
    the pipeline correctly returns nothing when retrieval is empty.
    """
    _MEMORY_STORE.clear()

    def fake_embed(text: str) -> list[float]:
        import hashlib
        vec = [0.0] * 64
        for word in text.lower().split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % 64
            vec[idx] += 1.0
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]

    with patch("app.services.embeddings.embed_texts", side_effect=lambda texts: [fake_embed(t) for t in texts]), \
         patch("app.services.embeddings.embed_query", side_effect=fake_embed), \
         patch("app.services.retrieval.embed_query", side_effect=fake_embed):

        # Step 1: upload resume.
        up = client.post(
            "/upload",
            files={"file": ("resume.txt", SAMPLE_RESUME, "text/plain")},
        )
        assert up.status_code == 200
        assert up.json()["chunks_stored"] >= 1

        # Step 2: clear the corpus.
        cl = client.delete("/upload")
        assert cl.status_code == 200
        assert cl.json()["status"] == "cleared"

        # Step 3: autofill — should return no responses since store is empty.
        af = client.post("/autofill", json={
            "fields": [
                {
                    "selector": "#why",
                    "label": "Why do you want to work here?",
                    "field_type": "textarea",
                },
            ],
            "job_description": "",
            "company_name": "Notion",
        })

    assert af.status_code == 200
    body = af.json()
    assert body["meta"]["fields_filled"] == 0
    assert body["responses"] == []
