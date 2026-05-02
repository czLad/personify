"""Smoke tests — verify the skeleton wires together."""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "personify-backend"


def test_autofill_stub_detects_personal_statement():
    r = client.post("/autofill", json={
        "fields": [
            {"selector": "#q1", "label": "Why do you want to work at Notion?", "field_type": "textarea"},
            {"selector": "#q2", "label": "First Name", "field_type": "text"},
        ],
        "job_description": "Building tools for thought.",
        "company_name": "Notion",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["responses"]) == 1
    assert body["responses"][0]["selector"] == "#q1"
