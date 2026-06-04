"""
Tests for the pipeline orchestration and the /autofill HTTP endpoint.

Scope:
  - HTTP wiring (/health, /, /autofill)
  - Pipeline behavior:
      * empty fields short-circuit
      * user_id threading + DEMO_USER_ID fallback
      * confidence threshold gates generation
      * prompt variant selection routes by question shape
      * query boost threads company + job description into retrieve
      * MMR cross-question diversity — used embeddings accumulate
        across the field loop and are passed as `penalize`
      * MMR scoring math at the retrieve() boundary
      * _build_query string construction
  - Classification is mocked; the LLM is never called here.

Upload-related tests live in test_upload.py; embedding-extraction tests
live in test_embeddings.py.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models.schemas import FormField
from app.services.classifier import FieldClassification
from app.services.embeddings import _MEMORY_STORE
from app.services.pipeline import (
    DEMO_USER_ID,
    MIN_CONFIDENCE,
    MMR_PENALTY_WEIGHT,
    RETRIEVAL_K,
    _pick_prompt_variant,
    run_autofill_pipeline,
)
from app.services.retrieval import RetrievedChunk, _build_query, retrieve
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
    even without a Gemini key.
    """
    from app.models.schemas import FieldResponse
    mock_pipeline.return_value = [
        FieldResponse(
            selector="#why",
            response="At NASA JPL I built a telemetry plotter in C++. The role here resonates.",
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


# ── Confidence threshold ─────────────────────────────────────

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
        assert "#high" in selectors
        assert "#low" not in selectors
        assert "#std" not in selectors

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
        get an essay. This is the safety guarantee.
        """
        mock_classify.return_value = [
            FieldClassification(selector="#a", classification="PERSONAL_STATEMENT", confidence=0.6),
        ]
        fields = [FormField(selector="#a", label="Tell us about a challenge", field_type="textarea")]
        assert run_autofill_pipeline(fields, "", "") == []


# ── Prompt variant selection ─────────────────────────────────

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
        variant, _ = _pick_prompt_variant("Tell us about yourself.")
        assert variant == "background"

    def test_each_variant_has_distinct_template(self):
        """Make sure the three templates aren't accidentally identical."""
        _, t_mot = _pick_prompt_variant("Why this company?")
        _, t_sto = _pick_prompt_variant("Describe a time when you led a team.")
        _, t_bkg = _pick_prompt_variant("Anything else?")
        assert t_mot != t_sto != t_bkg
        for t in (t_mot, t_sto, t_bkg):
            for placeholder in ("{company}", "{job_description}", "{context}", "{question}"):
                assert placeholder in t


# ── Query boost ──────────────────────────────────────────────────────

class TestQueryBoost:
    """
    Pipeline-level contract: when run_autofill_pipeline is given a company
    name and job description, those values must reach retrieve() so the
    embedding query can include role context.
    """

    FIELDS = [FormField(selector="#q1", label="Why this role?", field_type="textarea")]

    def _confident_classification(self):
        return [FieldClassification(
            selector="#q1", classification="PERSONAL_STATEMENT", confidence=0.9,
        )]

    @patch("app.services.pipeline.retrieve", return_value=[])
    @patch("app.services.pipeline.classify_fields")
    def test_company_threaded_to_retrieve(self, mock_classify, mock_retrieve):
        mock_classify.return_value = self._confident_classification()
        run_autofill_pipeline(self.FIELDS, job_description="", company_name="Notion")
        assert mock_retrieve.call_args.kwargs["company"] == "Notion"

    @patch("app.services.pipeline.retrieve", return_value=[])
    @patch("app.services.pipeline.classify_fields")
    def test_job_description_threaded_to_retrieve(self, mock_classify, mock_retrieve):
        mock_classify.return_value = self._confident_classification()
        run_autofill_pipeline(
            self.FIELDS,
            job_description="Building AI tooling for collaborative software with RAG.",
            company_name="Notion",
        )
        jd = mock_retrieve.call_args.kwargs["job_description"]
        assert "RAG" in jd
        assert "AI tooling" in jd

    @patch("app.services.pipeline.retrieve", return_value=[])
    @patch("app.services.pipeline.classify_fields")
    def test_empty_company_and_job_become_empty_strings(self, mock_classify, mock_retrieve):
        mock_classify.return_value = self._confident_classification()
        run_autofill_pipeline(self.FIELDS, job_description="", company_name="")
        assert mock_retrieve.call_args.kwargs["company"] == ""
        assert mock_retrieve.call_args.kwargs["job_description"] == ""

    @patch("app.services.pipeline.retrieve", return_value=[])
    @patch("app.services.pipeline.classify_fields")
    def test_retrieval_k_is_used(self, mock_classify, mock_retrieve):
        mock_classify.return_value = self._confident_classification()
        run_autofill_pipeline(self.FIELDS, job_description="", company_name="Notion")
        assert mock_retrieve.call_args.kwargs["k"] == RETRIEVAL_K


class TestBuildQuery:
    """Pure-string unit tests for _build_query."""

    def test_question_only_when_company_and_job_empty(self):
        assert _build_query("Why?", "", "") == "Why?"

    def test_company_appended_after_question(self):
        q = _build_query("Why?", "Notion", "")
        assert q.startswith("Why?")
        assert "Notion" in q

    def test_job_description_truncated_to_budget(self):
        long_jd = "a" * 1000
        q = _build_query("Why?", "", long_jd)
        assert q.count("a") == 200

    def test_all_three_components_included(self):
        q = _build_query("Why this role?", "Notion", "RAG and real-time AI features.")
        assert "Why this role?" in q
        assert "Notion" in q
        assert "RAG" in q

    def test_handles_whitespace_in_inputs(self):
        q = _build_query("Why?  ", "  Notion  ", "  Some JD  ")
        assert "  " not in q


# ── MMR cross-question diversity ─────────────────────────────────────

class TestMMRDeduplicationPipeline:
    """
    Pipeline-level contract: chunks selected for question N must appear
    as `penalize` embeddings on retrieve() for question N+1. This is the
    plumbing test — the math itself is tested in TestMMRScoring below.
    """

    @patch("app.services.pipeline.classify_fields")
    @patch("app.services.pipeline.retrieve")
    def test_first_call_has_no_penalize(self, mock_retrieve, mock_classify):
        """First retrieve() in a batch gets penalize=None (empty pool)."""
        mock_classify.return_value = [
            FieldClassification(selector="#q1", classification="PERSONAL_STATEMENT", confidence=0.9),
        ]
        mock_retrieve.return_value = [RetrievedChunk("c1", [0.1] * 768, 0.9)]
        fields = [FormField(selector="#q1", label="Why?", field_type="textarea")]
        run_autofill_pipeline(fields, "", "Notion")
        # `penalize` defaults to None when used_embeddings is empty
        assert mock_retrieve.call_args.kwargs["penalize"] is None

    @patch("app.services.pipeline.classify_fields")
    @patch("app.services.pipeline.retrieve")
    def test_subsequent_calls_receive_prior_embeddings(self, mock_retrieve, mock_classify):
        """Embeddings from earlier fields accumulate into penalize."""
        mock_classify.return_value = [
            FieldClassification(selector="#q1", classification="PERSONAL_STATEMENT", confidence=0.9),
            FieldClassification(selector="#q2", classification="PERSONAL_STATEMENT", confidence=0.9),
        ]
        emb1 = [0.1] * 768
        emb2 = [0.2] * 768
        # First field returns one chunk; second field returns another.
        mock_retrieve.side_effect = [
            [RetrievedChunk("chunk-1", emb1, 0.9)],
            [RetrievedChunk("chunk-2", emb2, 0.8)],
        ]
        fields = [
            FormField(selector="#q1", label="Why?", field_type="textarea"),
            FormField(selector="#q2", label="Describe a time", field_type="textarea"),
        ]
        run_autofill_pipeline(fields, "", "Notion")

        # First call: no penalize.
        first = mock_retrieve.call_args_list[0].kwargs
        assert first.get("penalize") is None

        # Second call: penalize contains the embedding from the first round.
        second = mock_retrieve.call_args_list[1].kwargs
        assert second.get("penalize") == [emb1]

    @patch("app.services.pipeline.classify_fields")
    @patch("app.services.pipeline.retrieve")
    def test_empty_embeddings_are_skipped(self, mock_retrieve, mock_classify):
        """
        Chunks from the pgvector path arrive with embedding=[] because the
        RPC doesn't surface them. Those must NOT enter the penalize pool —
        otherwise we'd accumulate empties and break later cosine math.
        """
        mock_classify.return_value = [
            FieldClassification(selector="#q1", classification="PERSONAL_STATEMENT", confidence=0.9),
            FieldClassification(selector="#q2", classification="PERSONAL_STATEMENT", confidence=0.9),
        ]
        mock_retrieve.side_effect = [
            [RetrievedChunk("pgvector-chunk", [], 0.0)],  # empty embedding
            [RetrievedChunk("another", [0.5] * 768, 0.7)],
        ]
        fields = [
            FormField(selector="#q1", label="Why?", field_type="textarea"),
            FormField(selector="#q2", label="Describe a time", field_type="textarea"),
        ]
        run_autofill_pipeline(fields, "", "Notion")

        # Second call's penalize should be None (no usable embeddings from first).
        second = mock_retrieve.call_args_list[1].kwargs
        assert second.get("penalize") is None

    @patch("app.services.pipeline.classify_fields")
    @patch("app.services.pipeline.retrieve")
    def test_penalty_weight_threaded(self, mock_retrieve, mock_classify):
        """The pipeline passes MMR_PENALTY_WEIGHT to retrieve every call."""
        mock_classify.return_value = [
            FieldClassification(selector="#q1", classification="PERSONAL_STATEMENT", confidence=0.9),
        ]
        mock_retrieve.return_value = []
        fields = [FormField(selector="#q1", label="Why?", field_type="textarea")]
        run_autofill_pipeline(fields, "", "Notion")
        assert mock_retrieve.call_args.kwargs["penalty_weight"] == MMR_PENALTY_WEIGHT


class TestMMRScoring:
    """
    Math at the retrieve() boundary. Sets _MEMORY_STORE directly with
    hand-picked embeddings so we can verify the penalty changes ranking.
    """

    def setup_method(self):
        _MEMORY_STORE.clear()

    def teardown_method(self):
        _MEMORY_STORE.clear()

    def test_no_penalize_preserves_pure_relevance_ranking(self):
        """penalize=None should behave exactly like the old top-k cosine."""
        query_emb = [1.0, 0.0, 0.0]
        _MEMORY_STORE["u1"] = [
            ("close", [0.95, 0.05, 0.0]),
            ("far",   [0.30, 0.95, 0.0]),
        ]
        with patch("app.services.retrieval.embed_query", return_value=query_emb):
            results = retrieve("q", "u1", k=2, penalize=None)
        assert results[0].content == "close"
        assert results[1].content == "far"

    def test_penalty_demotes_chunk_similar_to_used(self):
        """
        A chunk highly similar to an already-used embedding should drop in
        ranking. This is the core MMR contract.

        Vectors are chosen to make the math unambiguous:
          - query points mostly along axis-0 with a little of axis-1.
          - `used` and `chunk_a` are identical, so chunk_a takes the
            maximum possible penalty (cos(chunk_a, used) = 1).
          - `chunk_b` is orthogonal to `used`, so its penalty is 0.
        Without a penalty, chunk_a's higher query similarity wins.
        With a moderate penalty, chunk_a is dragged below chunk_b.
        """
        query_emb   = [3.0, 1.0, 0.0]
        used_emb    = [1.0, 0.0, 0.0]
        chunk_a_emb = [1.0, 0.0, 0.0]   # identical to `used` → max penalty
        chunk_b_emb = [0.0, 1.0, 0.0]   # orthogonal to `used` → zero penalty
        _MEMORY_STORE["u1"] = [
            ("chunk-a", chunk_a_emb),
            ("chunk-b", chunk_b_emb),
        ]
        with patch("app.services.retrieval.embed_query", return_value=query_emb):
            # Without penalty, chunk-a wins on raw query similarity.
            no_pen = retrieve("q", "u1", k=2, penalize=None)
            assert no_pen[0].content == "chunk-a"

            # With penalty against `used`, chunk-a takes a full -0.7 hit
            # while chunk-b takes none → chunk-b moves to the top.
            with_pen = retrieve(
                "q", "u1", k=2,
                penalize=[used_emb], penalty_weight=0.7,
            )
        assert with_pen[0].content == "chunk-b"

    def test_score_field_reflects_penalty(self):
        """The .score on RetrievedChunk should drop when a penalty is applied."""
        query_emb = [1.0, 0.0, 0.0]
        chunk_emb = [0.9, 0.1, 0.0]
        _MEMORY_STORE["u1"] = [("c", chunk_emb)]

        with patch("app.services.retrieval.embed_query", return_value=query_emb):
            no_pen = retrieve("q", "u1", k=1, penalize=None)
            with_pen = retrieve("q", "u1", k=1, penalize=[chunk_emb], penalty_weight=0.5)

        # With penalty, chunk's own embedding cosine to itself is 1.0, so:
        # score = no_pen.score - 0.5 * 1.0
        assert with_pen[0].score < no_pen[0].score
        assert abs((no_pen[0].score - with_pen[0].score) - 0.5) < 1e-6


class TestRetrievedChunkShape:
    """Smoke test on the return type so callers don't break silently."""

    def setup_method(self):
        _MEMORY_STORE.clear()

    def teardown_method(self):
        _MEMORY_STORE.clear()

    def test_in_memory_returns_retrieved_chunks_with_embeddings(self):
        _MEMORY_STORE["u1"] = [("hello", [0.1, 0.2, 0.3])]
        with patch("app.services.retrieval.embed_query", return_value=[1.0, 0.0, 0.0]):
            results = retrieve("q", "u1", k=1)
        assert len(results) == 1
        assert isinstance(results[0], RetrievedChunk)
        assert results[0].content == "hello"
        assert results[0].embedding == [0.1, 0.2, 0.3]
