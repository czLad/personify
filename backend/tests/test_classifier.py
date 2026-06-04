"""
Tests for the field classification service.

Covers:
  - heuristic_classify correctness
  - classify_fields heuristic fallback path (no Gemini key needed)
  - classify_fields LLM path (mocked)
  - pipeline integration: only PERSONAL_STATEMENT fields get responses
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import FormField
from app.services.classifier import (
    FieldClassification,
    classify_fields,
    heuristic_classify,
)
from app.services.pipeline import run_autofill_pipeline

# ── heuristic_classify ────────────────────────────────────────────────────────

class TestHeuristicClassify:
    def test_personal_statement_why(self):
        assert heuristic_classify("Why do you want to work here?") == "PERSONAL_STATEMENT"

    def test_personal_statement_tell_us(self):
        assert heuristic_classify("Tell us about yourself") == "PERSONAL_STATEMENT"

    def test_personal_statement_describe(self):
        assert heuristic_classify("Describe a challenge you overcame") == "PERSONAL_STATEMENT"

    def test_standard_email(self):
        assert heuristic_classify("Email address") == "STANDARD"

    def test_standard_name(self):
        assert heuristic_classify("Full name") == "STANDARD"

    def test_standard_gpa(self):
        assert heuristic_classify("GPA") == "STANDARD"

    def test_standard_linkedin(self):
        assert heuristic_classify("LinkedIn URL") == "STANDARD"

    def test_ambiguous_defaults_standard(self):
        # Unknown field label with no keywords → STANDARD (safe default)
        assert heuristic_classify("Additional information") == "STANDARD"


# ── classify_fields (heuristic fallback) ─────────────────────────────────────

class TestClassifyFieldsFallback:
    """Force LLM to fail so we exercise the heuristic fallback path."""

    FIELDS = [
        {"selector": "#q1", "label": "Why do you want to work here?", "field_type": "textarea"},
        {"selector": "#q2", "label": "Email address", "field_type": "text"},
        {"selector": "#q3", "label": "Tell us about a challenge", "field_type": "textarea"},
    ]

    @patch("app.services.classifier.llm_classify", side_effect=Exception("no api key"))
    def test_fallback_returns_all_fields(self, _mock):
        results = classify_fields(self.FIELDS)
        assert len(results) == 3

    @patch("app.services.classifier.llm_classify", side_effect=Exception("no api key"))
    def test_fallback_classifies_correctly(self, _mock):
        results = classify_fields(self.FIELDS)
        by_selector = {r.selector: r.classification for r in results}
        assert by_selector["#q1"] == "PERSONAL_STATEMENT"
        assert by_selector["#q2"] == "STANDARD"
        assert by_selector["#q3"] == "PERSONAL_STATEMENT"

    @patch("app.services.classifier.llm_classify", side_effect=Exception("no api key"))
    def test_fallback_confidence_marker(self, _mock):
        results = classify_fields(self.FIELDS)
        assert all(r.confidence == 0.6 for r in results)

    def test_empty_fields(self):
        assert classify_fields([]) == []


# ── classify_fields (LLM path) ────────────────────────────────────────────────

class TestClassifyFieldsLLM:
    FIELDS = [
        {"selector": "#q1", "label": "Why do you want to work here?", "field_type": "textarea"},
        {"selector": "#q2", "label": "Email address", "field_type": "text"},
    ]

    @patch("app.services.classifier.llm_classify")
    def test_llm_results_returned(self, mock_llm):
        mock_llm.return_value = [
            FieldClassification(selector="#q1", classification="PERSONAL_STATEMENT", confidence=0.95),
            FieldClassification(selector="#q2", classification="STANDARD", confidence=0.99),
        ]
        results = classify_fields(self.FIELDS)
        assert len(results) == 2
        assert results[0].classification == "PERSONAL_STATEMENT"
        assert results[1].classification == "STANDARD"

    @patch("app.services.classifier.llm_classify")
    def test_llm_called_with_correct_fields(self, mock_llm):
        mock_llm.return_value = []
        classify_fields(self.FIELDS)
        mock_llm.assert_called_once_with(self.FIELDS)


# ── pipeline integration ──────────────────────────────────────────────────────

class TestPipelineClassifyIntegration:
    """
    Test that pipeline only returns responses for PERSONAL_STATEMENT fields.
    Mocks classify_fields so no LLM key needed.
    """

    FIELDS = [
        FormField(selector="#f1", label="Why do you want to work here?", field_type="textarea"),
        FormField(selector="#f2", label="Email address", field_type="text"),
        FormField(selector="#f3", label="Describe your background", field_type="textarea"),
    ]

    @patch("app.services.pipeline.classify_fields")
    def test_only_personal_statement_fields_returned(self, mock_classify):
        mock_classify.return_value = [
            FieldClassification(selector="#f1", classification="PERSONAL_STATEMENT", confidence=0.95),
            FieldClassification(selector="#f2", classification="STANDARD", confidence=0.99),
            FieldClassification(selector="#f3", classification="PERSONAL_STATEMENT", confidence=0.9),
        ]
        results = run_autofill_pipeline(self.FIELDS, "We build dev tools", "Notion")
        selectors = [r.selector for r in results]
        assert "#f1" in selectors
        assert "#f2" not in selectors
        assert "#f3" in selectors

    @patch("app.services.pipeline.classify_fields")
    def test_empty_fields_returns_empty(self, mock_classify):
        results = run_autofill_pipeline([], "", "")
        assert results == []
        mock_classify.assert_not_called()

    @patch("app.services.pipeline.classify_fields")
    def test_all_standard_returns_empty(self, mock_classify):
        mock_classify.return_value = [
            FieldClassification(selector="#f2", classification="STANDARD", confidence=0.99),
        ]
        results = run_autofill_pipeline(
            [FormField(selector="#f2", label="Email", field_type="text")],
            "",
            "Stripe",
        )
        assert results == []
