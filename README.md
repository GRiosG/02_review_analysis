# Product Review Analyzer API

A production-grade REST API that extracts structured intelligence from customer reviews:
themes, sentiment, pain points and feature requests, powered by Gemini Flash and built with FastAPI.

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
**Prerequisites:**
- Python 3.11+
- `uv`
- Gemini Studio API key (paid or free)

```bash
git clone https://github.com/YOUR_USERNAME/product-review-analyzer
cd product-review-analyzer

# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# Run
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

---

## Trying it out (Docker):

```bash
docker build -t review-analyzer .
docker run -p 8000:8000 --env-file .env review-analyzer
```

## API reference:
### `POST /analyze`

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
  -d '{"reviews": ["Amazing product, love the build quality!", "Too expensive for what it offers."], "product_name": "Widget Pro"}'
```

### `GET /health`
Returns `{"status": "ok"}`. Used as a liveness probe by load balancers.

---

## Key engineering concepts

**Structured LLM output** — `response_schema=GeminiAnalysis` in the
`GenerateContentConfig` forces Gemini to return JSON matching the Pydantic
model exactly.

**Docker layer caching with uv** — dependency files are copied and installed
*before* source code. A code-only change hits the dependency cache and
only re-runs the final `COPY app/`. Cold builds are fast because uv is
10–100× faster than pip.

**JSON logging for the cloud** — every log line is a JSON object with
`timestamp`, `level`, `status_code`, `latency_ms`, and `request_id`.
Cloud platforms (GCP, AWS, Azure) index these fields automatically,
enabling dashboards and alerts without any extra parsing configuration.

---

## License

MIT