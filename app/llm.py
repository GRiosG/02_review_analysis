from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import types
from openai import AsyncOpenAI

from app.config import settings
from app.schemas import GeminiAnalysis

# logger object initialization
logger = logging.getLogger(__name__)

# LLM timeout (how long to wait for a provider before giving up and trying fallback
LLM_TIMEOUT_SECONDS = 10.0


class AllProvidersFailedError(Exception):
    """
    This is raised when every provider (main and fallback) in the chain has been tried and failed.
    Caught specifically in main.py and mapped to a 503 Service Unavailable.

    This is kept in llm.py (not a separate exceptions.py) because it's tightly coupled to the analyzer logic.
    """
    pass


class ReviewAnalyzer:
    """
    Owns all LLM interaction logic.
    Instantiated once at app startup (main.py lifespam) and stored on app.state.

    LLM provider chain: Gemini (primary) -> OpenAI (fallback if configured)
    Each provider has a timeout. A failure at any point moves to the next.
    """

    def __init__(self) -> None:
        # primary: Gemini - required
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set!"
            )
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

        # fallback: OpenAI (optional)
        # no raise here because its absence just means there's no fallback available.
        self.openai_client = (
            AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            if settings.OPENAI_API_KEY
            else None
        )

        if self.openai_client is None:
            logger.warning(
                "no_fallback_configured",
                extra={"detail": "OPENAI_API_KEY not set - no fallback provider available"},
            )


    def _build_prompt(self, reviews: list[str], product_name: str | None = None) -> str:
        """
        Builds and returns a prompt based on input reviews and product.
        """
        product_ctx = f" for the product '{product_name}'" if product_name else ""
        numbered_reviews = "\n".join(
            f"{i + 1}. {review}" for i, review in enumerate(reviews)
        )

        return f"""You are a senior product analyst. Analyze the following \
        {len(reviews)} customer review(s){product_ctx}.

        REVIEWS:
        {numbered_reviews}

        Return a JSON object with:
        - overall_sentiment: positive / negative / mixed / neutral
        - sentiment_score: float from -1.0 (very negative) to 1.0 (very positive)
        - themes: list of main topics mentioned across reviews
        - pain_points: list of specific problems and frustrations mentioned
        - feature_requests: list of features or improvements customers want
        - summary: 2-3 sentence plain-English summary of the overall picture
        """

    async def _try_gemini(self, reviews: list[str], product_name: str | None) -> GeminiAnalysis:
        """
        asyncio.wait_for wraps the call with a hard timeout.
        If Gemini doesn't respond within LLM_TIMEOUT_SECONDS, it raises asyncio.TimeoutError, which is
        treated as any other failure in the analyze() function.
        """
        response = await asyncio.wait_for(
            self.gemini_client.aio.models.generate_content(
                model=self.gemini_model,
                contents=self._build_prompt(reviews, product_name),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiAnalysis,
                ),
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        return GeminiAnalysis.model_validate_json(response.text)

    async def _try_openai(self, reviews: list[str], product_name: str | None) -> GeminiAnalysis:
        """
        OpenAI does not support response_schema like Gemini.
        response_format={"type": "json_object"} enforces valid JSON output,
        but not the specific shape (for that there's model_validate_json())
        """
        response = await asyncio.wait_for(
            self.openai_client.chat.completions.create(
                model=self.openai_model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "You are a senior product analyst. Always respond with valid JSON only.",
                    },
                    {
                        "role": "user",
                        "content": self._build_prompt(reviews, product_name),
                    },
                ],
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        return GeminiAnalysis.model_validate_json(response.choices[0].message.content)

    async def analyze(self,reviews: list[str], product_name: str | None = None) -> tuple[GeminiAnalysis, str]:
        """
        Returns (analysis, model_name_used) so the handler can tell the client
        which provider actually served the request.

        Try chain:
            1. Gemini  → timeout + any exception triggers fallback
            2. OpenAI  → only attempted if configured
            3. AllProvidersFailedError raised → handler maps to 503
        """

        # attempt 1: Gemini
        try:
            result = await self._try_gemini(reviews, product_name)
            logger.info("llm_success", extra={"provider": "gemini"})
            return result, self.gemini_model
        except Exception as exc:
            logger.warning(
                "primary_provider_failed",
                extra={"provider": "gemini", "error": str(exc)},
            )

        # attempt 2: OpenAI fallback
        if self.openai_client is not None:
            try:
                result = await self._try_openai(reviews, product_name)
                logger.info("llm_success", extra={"provider": "openai_fallback"})
                return result, self.openai_model
            except Exception as exc:
                logger.warning(
                    "fallback_provider_failed",
                    extra={"provider": "openai", "error": str(exc)},
                )

        # all providers exhausted
        raise AllProvidersFailedError(
            "All configured LLM providers are unavailable."
        )