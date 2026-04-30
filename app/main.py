from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.llm import AllProvidersFailedError, ReviewAnalyzer
from app.schemas import ReviewRequest, ReviewResponse


# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------


class JSONFormatter(logging.Formatter):
    _SKIP = frozenset(
        {
            *logging.LogRecord("", 0, "", 0, "", (), None).__dict__,
            "message",
            "asctime",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        log: dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, val in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                log[key] = val
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log)


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL)

    # Take over Uvicorn's loggers so all output is JSON
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True


_setup_logging()
logger = logging.getLogger(__name__)


# Rate limiter
# slowapi's Limiter wraps the `limits` library.
# key_func=get_remote_address: limits per client IP.
# This is the right key for a public API — each IP gets its own counter.
limiter = Limiter(key_func=get_remote_address)



# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "starting up",
        extra={
            "env": settings.APP_ENV,
            "model": settings.GEMINI_MODEL,
            "rate_limit": settings.RATE_LIMIT,
        },
    )
    app.state.analyzer = ReviewAnalyzer()

    # slowapi requires the limiter on app.state — it reads it internally
    # when processing @limiter.limit() decorated routes.
    # This must happen in lifespan, not at module level, because app.state
    # isn't available until the app is created.
    app.state.limiter = limiter

    yield
    logger.info("shutting down")


# FastAPI app
app = FastAPI(
    title="Product Review Analyzer",
    description=(
        "Extract themes, sentiment, pain points, and feature requests "
        "from customer reviews using Gemini 2.0 Flash with OpenAI fallback."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Register the rate limit exceeded handler.
# When a client hits the limit, slowapi raises RateLimitExceeded.
# This handler catches it and returns a clean 429 Too Many Requests response
# instead of letting it bubble up to the global exception handler as a 500.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)



# Middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    response = await call_next(request)

    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )

    response.headers["X-Request-ID"] = request_id
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        extra={"path": request.url.path, "error": str(exc)},
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# Routes
@app.get("/health", tags=["Ops"], summary="Liveness probe")
async def health_check():
    return {"status": "ok"}


@app.post(
    "/analyze",
    response_model=ReviewResponse,
    status_code=status.HTTP_200_OK,
    tags=["Analysis"],
    summary="Analyze customer reviews",
)
@limiter.limit(settings.RATE_LIMIT)
# This decorator reads the limit string from config ("10/minute")
# and enforces it per IP using the counter stored in app.state.limiter.
# When the limit is exceeded, RateLimitExceeded is raised automatically
# and caught by the handler registered above — your code never sees it.
# IMPORTANT: when using @limiter.limit, `request: Request` MUST be the
# first parameter. slowapi needs to inspect it to extract the client IP.
async def analyze_reviews(request: Request, payload: ReviewRequest):
    analyzer: ReviewAnalyzer = request.app.state.analyzer

    try:
        analysis, model_used = await analyzer.analyze(
            payload.reviews,
            payload.product_name,
        )
    except AllProvidersFailedError:
        # Every provider was tried and failed.
        # We already logged warnings per provider in llm.py — no need to log again.
        # 503: the service is temporarily unavailable (accurate — it's not our fault)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analysis is temporarily unavailable. All providers are down. Please try again later.",
        )
    except Exception as exc:
        logger.error(
            "unexpected_error",
            extra={"error": str(exc)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to analyze reviews. Unexpected error.",
        )

    return ReviewResponse(
        product_name=payload.product_name,
        review_count=len(payload.reviews),
        model_used=model_used,
        analysis=analysis,
    )