# Product Review Analyzer API

A production-grade REST API that extracts structured intelligence from customer reviews — themes, sentiment, 
pain points, and feature requests — powered by **Gemini 2.0 Flash** with **OpenAI fallback**, built with **FastAPI**.

## Features:
- Structured LLM output with Pydantic schema enforcement
- async FastAPI middleware for JSON request logging
- Docker multi-stage builds with `uv`

---
## Tech stack:

| Layer | Tool |
|---|---|
| API-framework | FastAPI + Uvicorn |
| LLM | Gemini Flash (google-genai) |
| Validation | Pydantic v2 |
| Package manager | uv |
| Containerization | Docker (multi-stage) |
| Logging | Structured JSON (cloud-ready) |
---

## Project structure:
```
app/
├── config.py     # Settings singleton via python-dotenv
├── schemas.py    # Pydantic models: request, LLM output, response
├── llm.py        # ReviewAnalyzer class — Gemini client & prompt logic
└── main.py       # FastAPI app, JSON middleware, routes
```

## Trying it out (local):
**Prerequisites:** Python 3.13+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
git clone https://github.com/YOUR_USERNAME/product-review-analyzer
cd product-review-analyzer

# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env — GEMINI_API_KEY is required, OPENAI_API_KEY is optional (fallback)

# Run
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

---

## Quick start (Docker)

```bash
docker build -t review-analyzer .
docker run -p 8000:8000 --env-file .env review-analyzer
```

---

## API reference

### `POST /analyze`

Analyze a batch of customer reviews. Rate limited per client IP.

**Request body:**
```json
{
  "reviews": [
    "Great battery life but the camera is disappointing.",
    "Wish it had a headphone jack. Screen is gorgeous though."
  ],
  "product_name": "Pixel 9"
}
```

**Response:**
```json
{
  "product_name": "Pixel 9",
  "review_count": 2,
  "model_used": "gemini-2.0-flash",
  "analysis": {
    "overall_sentiment": "mixed",
    "sentiment_score": 0.1,
    "themes": ["battery life", "camera quality", "display", "audio"],
    "pain_points": ["disappointing camera", "no headphone jack"],
    "feature_requests": ["headphone jack"],
    "summary": "Customers appreciate the battery life and screen quality but are disappointed with the camera. The missing headphone jack is a recurring complaint."
  }
}
```

**curl example:**
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "reviews": [
      "Amazing product, love the build quality!",
      "Too expensive for what it offers."
    ],
    "product_name": "Widget Pro"
  }'
```

**Error responses:**

| Status | Meaning |
|---|---|
| `422 Unprocessable Entity` | Request body failed validation |
| `429 Too Many Requests` | Rate limit exceeded for your IP |
| `503 Service Unavailable` | All LLM providers are temporarily unavailable |

### `GET /health`

Returns `{"status": "ok"}`. Used as a liveness probe by load balancers and container orchestrators.

---

## Key engineering concepts

**Provider fallback chain**
Requests go to Gemini first. If Gemini fails (error or timeout), the request
is automatically retried with OpenAI. If both fail, a `503` is returned with
a human-readable message. Each provider has a hard 10-second timeout enforced
via `asyncio.wait_for` — a slow provider can't hold the event loop indefinitely.

**Structured LLM output**
`response_schema=GeminiAnalysis` in the `GenerateContentConfig` forces Gemini
to return JSON matching the Pydantic model exactly. No brittle string parsing.
OpenAI uses `response_format={"type": "json_object"}` and the output is then
validated against the same Pydantic model.

**Rate limiting**
`slowapi` enforces per-IP request limits using an in-memory counter. The limit
is configurable via `RATE_LIMIT` in `.env`. For multi-worker deployments,
replace the default in-memory store with Redis to share counters across processes.

**Docker layer caching with uv**
Dependency files are copied and installed before source code. A code-only
change hits the dependency cache — only the final `COPY app/` re-runs.

**JSON logging for the cloud**
Every log line is a JSON object with `timestamp`, `level`, `status_code`,
`latency_ms`, and `request_id`. Cloud platforms (GCP, AWS, Azure) index
these fields automatically, enabling dashboards and alerts without extra
parsing configuration.

---

## License

MIT