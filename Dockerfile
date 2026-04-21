# syntax=docker/dockerfile:1

# Stage 1 - dependency builder -----------------------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Pulling uv directly from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Layer caching
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-cache

# Stage 2 - runtime image
# Copies only the build venv and application code. No uv, no build tools, no cache to keep the image lean.
FROM python:3.11-slim

WORKDIR /app

# Copy the pre-built virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY app/ ./app/

# Don't buffer stdout/stderr - critical for JSON log streaming
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]