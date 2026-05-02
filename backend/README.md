# Personify Backend

Python + FastAPI service that powers the agentic pipeline.

## Layout

```
backend/
├── main.py                 FastAPI app entrypoint
├── app/
│   ├── core/config.py      Settings loaded from .env
│   ├── routers/            HTTP endpoints
│   │   ├── health.py       GET  /health
│   │   ├── auth.py         POST /auth/{signup,login}
│   │   ├── upload.py       POST /upload
│   │   ├── autofill.py     POST /autofill   ← the agentic loop
│   │   └── history.py      GET  /history
│   ├── services/
│   │   └── pipeline.py     LangChain pipeline (currently a stub)
│   └── models/schemas.py   Pydantic request/response models
└── tests/                  Smoke tests
```

## Quickstart

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then fill in keys
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the auto-generated Swagger UI.

## Run tests

```bash
pytest
```

## What's implemented vs stubbed

| Endpoint | Status |
|---|---|
| `GET /health` | ✅ implemented |
| `POST /autofill` | ✅ stubbed — returns mock responses for personal-statement-looking labels |
| `POST /upload` | ⏳ stubbed — accepts file but doesn't embed |
| `POST /auth/signup` and `/auth/login` | ⏳ stubbed — returns 501 |
| `GET /history` | ⏳ stubbed — returns empty list |

See `docs/ROADMAP.md` for the build order.
