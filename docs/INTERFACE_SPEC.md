# `/autofill` — Interface Specification

This document is the source-of-truth contract between the Chrome extension
and the backend pipeline. The frontend dashboard does not use this
endpoint; it talks to `/upload`, `/history`, and `/health` only.

Promised in Week 6 weekly report. Companion spec for `/upload` is
inlined in the docstring of `app/routers/upload.py`.

---

## Endpoint

```
POST /autofill
```

## Request

### Headers

| Name           | Type   | Required | Meaning                                                                                 |
|----------------|--------|----------|-----------------------------------------------------------------------------------------|
| `Content-Type` | string | yes      | Must be `application/json`.                                                              |
| `X-User-Id`    | string | no       | Identifies which user's uploaded documents to retrieve. Defaults to `"demo-user"` until auth is wired. |

### Body

```json
{
  "fields": [
    {
      "selector": "#why",
      "label": "Why do you want to work at Notion?",
      "field_type": "textarea"
    }
  ],
  "job_description": "Notion builds tools for thought...",
  "company_name": "Notion"
}
```

| Field                 | Type                | Required | Meaning                                                                                          |
|-----------------------|---------------------|----------|--------------------------------------------------------------------------------------------------|
| `fields`              | array of `FormField`| yes      | Form fields scraped from the application page.                                                   |
| `fields[].selector`   | string              | yes      | Composite key (id + label + DOM position) the content script will use to locate the field again.|
| `fields[].label`      | string              | yes      | The visible label or question text. Used both for classification and as the prompt to the LLM.   |
| `fields[].field_type` | string              | no       | `"text"`, `"textarea"`, etc. Informational; defaults to `"text"`.                                |
| `job_description`     | string              | no       | Scraped job description; truncated to 2000 chars inside the prompt. Default `""`.                |
| `company_name`        | string              | no       | Best-guess company name. Injected into the prompt. Default `""`.                                 |

## Response — `200 OK`

```json
{
  "responses": [
    {
      "selector": "#why",
      "response": "I'm drawn to Notion because...",
      "classification": "PERSONAL_STATEMENT"
    }
  ],
  "meta": {
    "fields_received": 3,
    "fields_filled": 1,
    "pipeline_version": "0.2-langchain-rag",
    "user_id": "demo-user"
  }
}
```

| Field                          | Type    | Meaning                                                                                  |
|--------------------------------|---------|------------------------------------------------------------------------------------------|
| `responses`                    | array   | One entry per field that was both classified `PERSONAL_STATEMENT` AND met the confidence threshold. Standard fields and low-confidence fields are silently absent. |
| `responses[].selector`         | string  | Matches the input selector exactly — clients use this to map back to the DOM element.    |
| `responses[].response`         | string  | The generated answer (~100 words). May contain a `[Gemini API key not configured...]` placeholder if the server has no key. |
| `responses[].classification`   | string  | Always `"PERSONAL_STATEMENT"` in this version. Reserved for future categories.            |
| `meta.fields_received`         | int     | How many fields the request contained.                                                   |
| `meta.fields_filled`           | int     | How many of those got a generated response.                                              |
| `meta.pipeline_version`        | string  | Bumped whenever the pipeline contract changes meaningfully. Clients can branch on it.    |
| `meta.user_id`                 | string  | The user_id actually used (`DEMO_USER_ID` when no `X-User-Id` was sent).                 |

## Semantics

For each field, the server:

1. **Classifies** with a Gemini-backed classifier; falls back to a keyword
   heuristic on any failure. Each classification carries a confidence in
   `[0.0, 1.0]`.
2. **Gates on confidence.** Only fields with `classification == "PERSONAL_STATEMENT"` AND
   `confidence >= MIN_CONFIDENCE` (currently 0.7) proceed. This avoids
   pasting essays into ambiguous fields. Heuristic-fallback results sit
   at 0.6 by design, so when the LLM is unavailable the server is
   intentionally conservative and skips rather than guess.
3. **Retrieves** the top-`k` most relevant chunks (default `k=4`) from
   the user's uploaded resume/essays via RAG (pgvector if configured,
   in-memory otherwise). The embedding query is **not** just the field's
   question — it is the question concatenated with `company_name` and a
   truncated slice of `job_description` (200 chars). This gives technical
   resume chunks a fair chance against narrative essay chunks on
   role-specific questions. The boost is internal and the request shape
   is unchanged.
4. **Generates** a ~100 word response using one of three prompt variants
   selected by lexical cues in the question:
   - `motivation` — matches "why...", "what excites...", "interested in"
   - `story`      — matches "describe a time/challenge", "tell us about a time"
   - `background` — everything else

The order of items in `responses` is **not** guaranteed to match the
input field order. Clients **must** use `selector` to map responses back.

## Errors

| Status | Cause                                        | Body                                                                 |
|--------|----------------------------------------------|----------------------------------------------------------------------|
| 422    | Body fails Pydantic validation               | Standard FastAPI validation error                                    |
| 200    | `GEMINI_API_KEY` not configured              | `response` field contains `[Gemini API key not configured...]`        |
| 200    | Gemini call raised (rate limit, network)     | `response` field contains `[Generation failed: ...]`                  |
| 500    | Unhandled exception                          | FastAPI default error body                                            |

A 4xx is never returned for a single field's generation failure — partial
success is the norm. Clients should treat the absence of a response for
a given selector as either "this field wasn't a personal statement",
"the classifier wasn't confident enough", or "generation failed silently".

## Hidden implementation details (intentionally not in the contract)

The endpoint deliberately does NOT expose:

* Which LLM is used (Gemini vs anything else)
* Which prompt variant was chosen for a given field
* Whether RAG retrieval came from pgvector or the in-memory fallback
* The user's actual resume text or any embeddings
* The classifier's confidence score per field

These are all internal so we can swap implementations without coordinating
a contract change with the extension or frontend teams. See the Week 5
report on narrow interfaces.

## Versioning

`meta.pipeline_version` follows semver-ish strings:

* `"0.1-mock"` — original deterministic stub
* `"0.2-langchain-rag"` — current production behavior

Bumps to the leading number signal a breaking contract change. Clients
should refuse to use a pipeline version they don't recognize.