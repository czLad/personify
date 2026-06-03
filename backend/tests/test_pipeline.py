"""
Tests for the pipeline orchestration and the /autofill HTTP endpoint.

Scope after the test-file split:
  - HTTP wiring (/health, /, /autofill)
  - Pipeline behavior:
      * empty fields short-circuit
      * user_id threading + DEMO_USER_ID fallback
      * confidence threshold gates generation (Week 4 promise)
      * prompt variant selection routes by question shape (Week 4 promise)
  - Classification is mocked; the LLM is never called here.

Upload-related tests live in test_upload.py; embedding-extraction tests
live in test_embeddings.py.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models.schemas import FormField
from app.services.classifier import FieldClassification
from app.services.pipeline import (
    DEMO_USER_ID,
    MIN_CONFIDENCE,
    _pick_prompt_variant,
    run_autofill_pipeline,
)
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


# ── /autofill HTTP endpoint (placeholder text is fine without API key) ────────

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


@patch("app.routers.autofill.run_autofill_pipeline")
def test_autofill_targets_personal_statement_fields(mock_pipeline):
    """
    A confident PERSONAL_STATEMENT field should round-trip through the
    HTTP layer correctly. We mock the pipeline so this test runs cleanly
    even without a Gemini key — otherwise the live heuristic fallback
    returns 0.6 confidence, which the new threshold gate correctly
    blocks (see TestConfidenceThreshold below).
    """
    from app.models.schemas import FieldResponse
    mock_pipeline.return_value = [
        FieldResponse(
            selector="#why",
            response="I'm drawn to Notion because of its emphasis on craft.",
            classification="PERSONAL_STATEMENT",
        ),
    ]

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
    assert body["meta"]["fields_received"] == 2
    assert body["meta"]["fields_filled"] == 1


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


# ── Confidence threshold (Week 4 promise) ─────────────────────────────────────

class TestConfidenceThreshold:
    """
    Behavior contract:
      * confidence >= MIN_CONFIDENCE → field gets a response
      * confidence <  MIN_CONFIDENCE → field is silently skipped
      * STANDARD fields are skipped regardless of confidence
    """

    FIELDS = [
        FormField(selector="#high", label="Why do you want to work here?", field_type="textarea"),
        FormField(selector="#low",  label="Tell us anything else",          field_type="textarea"),
        FormField(selector="#std",  label="Email address",                  field_type="text"),
    ]

    @patch("app.services.pipeline.retrieve", return_value=[])
    @patch("app.services.pipeline.classify_fields")
    def test_low_confidence_personal_statement_is_skipped(self, mock_classify, _retrieve):
        mock_classify.return_value = [
            FieldClassification(selector="#high", classification="PERSONAL_STATEMENT", confidence=0.95),
            FieldClassification(selector="#low",  classification="PERSONAL_STATEMENT", confidence=0.55),
            FieldClassification(selector="#std",  classification="STANDARD",           confidence=0.99),
        ]
        results = run_autofill_pipeline(self.FIELDS, "", "Notion")
        selectors = [r.selector for r in results]
        assert "#high" in selectors        # confident PS fills
        assert "#low" not in selectors     # low-confidence PS is dropped
        assert "#std" not in selectors     # standard fields always dropped

    @patch("app.services.pipeline.retrieve", return_value=[])
    @patch("app.services.pipeline.classify_fields")
    def test_threshold_boundary_inclusive(self, mock_classify, _retrieve):
        """Confidence == MIN_CONFIDENCE should pass (>= comparison)."""
        mock_classify.return_value = [
            FieldClassification(selector="#high", classification="PERSONAL_STATEMENT", confidence=MIN_CONFIDENCE),
        ]
        fields = [FormField(selector="#high", label="Why?", field_type="textarea")]
        assert len(run_autofill_pipeline(fields, "", "")) == 1

    @patch("app.services.pipeline.retrieve", return_value=[])
    @patch("app.services.pipeline.classify_fields")
    def test_heuristic_fallback_confidence_is_blocked(self, mock_classify, _retrieve):
        """
        Heuristic classifier returns 0.6 — that's deliberately below
        MIN_CONFIDENCE (0.7), so a heuristic-classified PS should NOT
        get an essay. This is the safety guarantee from Week 4.
        """
        mock_classify.return_value = [
            FieldClassification(selector="#a", classification="PERSONAL_STATEMENT", confidence=0.6),
        ]
        fields = [FormField(selector="#a", label="Tell us about a challenge", field_type="textarea")]
        assert run_autofill_pipeline(fields, "", "") == []


# ── Prompt variant selection (Week 4 promise) ─────────────────────────────────

class TestPromptVariantSelection:
    """
    _pick_prompt_variant routes a question to one of three templates based
    on lexical cues. The choice is deterministic so it can be tested
    without ever hitting the LLM.
    """

    def test_motivation_variant_for_why_questions(self):
        variant, _ = _pick_prompt_variant("Why do you want to work at Notion?")
        assert variant == "motivation"

    def test_motivation_variant_for_interested_in(self):
        variant, _ = _pick_prompt_variant("What are you interested in about this role?")
        assert variant == "motivation"

    def test_story_variant_for_describe_a_time(self):
        variant, _ = _pick_prompt_variant("Describe a time you faced a hard tradeoff.")
        assert variant == "story"

    def test_story_variant_for_tell_us_about_a_challenge(self):
        variant, _ = _pick_prompt_variant("Tell us about a challenge you overcame.")
        assert variant == "story"

    def test_background_variant_for_open_ended(self):
        # No "why"/"describe" cue → background bucket.
        variant, _ = _pick_prompt_variant("Tell us about yourself.")
        assert variant == "background"

    def test_each_variant_has_distinct_template(self):
        """Make sure the three templates aren't accidentally identical."""
        _, t_mot = _pick_prompt_variant("Why this company?")
        _, t_sto = _pick_prompt_variant("Describe a time when you led a team.")
        _, t_bkg = _pick_prompt_variant("Anything else?")
        assert t_mot != t_sto != t_bkg
        # And all share the base scaffold placeholders.
        for t in (t_mot, t_sto, t_bkg):
            for placeholder in ("{company}", "{job_description}", "{context}", "{question}"):
                assert placeholder in t