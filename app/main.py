from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from xml.sax import handler

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.llm import ReviewAnalyzer
from app.schemas import ReviewResponse, ReviewRequest

# Structured JSON logging setup ----------------------------------------------------------------------------------------
class JSONFormatter(logging.Formatter):
    """
    Replaces python's default human-readable log format with single-line JSON (for Cloud logging)
    """

    # Std LogRecord attributes - skipped when extracting extra fields
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
        # Merging any extra= fields from the logger call into the JSON object.
        for key, val in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                log[key] = val
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log)


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler] # replace any default handlers
    root.setLevel(settings.LOG_LEVEL)

_setup_logging() # called at import time, before any other module logs anything...
logger = logging.getLogger(__name__)

# Lifespan: startup / shutdown -----------------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    ReviewAnalyzer is created here -once- and attached to app.state.
    Every request handler can then access it via request.app.state.analyzer without recreating the Gemini client
    each time.
    """
    logger.info("starting up", extra = {"env": settings.APP_ENV, "model": settings.GEMINI_MODEL})
    app.state.analyzer = ReviewAnalyzer()
    yield
    logger.info("shutting down")

# FastAPI app ----------------------------------------------------------------------------------------------------------
app = FastAPI(
    title = "Product Review Analyzer",
    description = (
        "Extract themes, sentiment, pain points and feature requests from customer reviews using Gemini Flash."
    ),
    version= "1.0.0",
    lifespan=lifespan
)

# Middleware: request/response logging with latency --------------------------------------------------------------------
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    This wraps every incoming HTTP request.

    The pattern is:
        start_time = ... <- before the rest of the app runs
        response = await call_next(request) <- entire stack runs here
        latency = ... <- after the response is ready

    `call_next(request)` triggers: router lookup -> dependency injection -> Pydantic validation -> the handler ->
    Pydantic output serialization.

    Everything between start_time and the latency calculation is observed and logged.

    X-Request-ID is injected into every response header so distributed tracing systems can correlate logs to requests.
    """

    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    response = await call_next(request)

    latency_ms = round((time.perf_counter() - start) * 1000,2)

    logger.info(
        "request",
        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )

    response.headers["X-Request-ID"] = request_id
    return response

# Exception handler ----------------------------------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches any unhandled exception and returns a clean 500.
    Without this, FastAPI would return the raw python traceback as a string,
    which leaks internal details and breaks structured JSON logging.
    """
    logger.error(
        "unhandled exception",
        extra = {"path": request.url, "error": str(exc)},
        exc_info=True,
    )
    return JSONResponse(
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
        content = {"detail": "Internal server error"},
    )

# Routes ---------------------------------------------------------------------------------------------------------------
@app.get("/health", tags=["Ops"], summary = "Liveness probe")
async def health_check():
    """Returns 200 OK"""
    return {"status": "ok"}

@app.post(
    "/analyze",
    response_model = ReviewResponse,
    status_code = status.HTTP_200_OK,
    tags = ["Analysis"],
    summary = "Analyze customer reviews",
    description = (
        "Submit a list of customer review texts. Returns themes, sentiment score, pain points and feature requests."
    ),
)
async def analyze_reviews(payload: ReviewRequest, request: Request):
    """
    `payload: ReviewRequest` - FastAPI automatically validates the JSON body against ReviewRequest before this function
    is called. A 422 is returned automatically if validation fails -> there should never be invalid data.

    `request: Request` - gives access to app.state where the ReviewAnalyzer singleton at the start.
    """

    analyzer: ReviewAnalyzer = request.app.state.analyzer

    try:
        analysis = await analyzer.analyze(payload.reviews, payload.product_name)
    except Exception as exc:
        # Catching Gemini API errors (network, quota, etc.) and return 502
        logger.error("gemini api error", extra = {"error": str(exc)}, exc_info=True)
        raise HTTPException(
            status_code = status.HTTP_502_BAD_GATEWAY,
            detail = "Failed to analyze reviews. Upstream LLM error."
        )

    return ReviewResponse(
        product_name = payload.product_name,
        review_count = len(payload.reviews),
        model_used = analyzer.model,
        analysis = analysis,
    )