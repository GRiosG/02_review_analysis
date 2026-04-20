from __future__ import annotations

from google import genai
from google.genai import types

from app.config import settings
from app.schemas import GeminiAnalysis

class ReviewAnalyzer:
    """
    Wraps the Gemini client and owns all prompt logic.
    Instantiated once at app startup (main.py lifespam) and stored on app.state, so that genai.Client is created
    once and not everytime there's a request.
    """

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set!"
            )
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    async def analyze(self, reviews: list[str], product_name: str | None = None) -> GeminiAnalysis:
        """
        Builds a prompt and gives a call to Gemini asynchronously. Returns a validated GeminiAnalysis
        Pydantic model.
        """
        product_ctx = f" for the product '{product_name}'" if product_name else ""
        numbered_reviews = "\n".join(
            f"{i+1}. {review}}" for i, review in enumerate(reviews)
        )

        prompt = f"""You are a senior product analyst. Analyze the following {len(reviews)} customer 
        review(s) {product_ctx}.

        REVIEWS:
        {numbered_reviews}

        Return a JSON object containing:
        - overall_sentiment: general sentiment (positive / negative / mixed / neutral)
        - sentiment_score: float from -1.0 (very negative) to 1.0 (very positive)
        - themes: list of the main topics mentioned across reviews
        - pain_points: list of specific problems and frustrations mentioned
        - feature_requests: list of features or improvements customers want
        - summary: 2-3 sentence plain-English summary of what the reviews say overall
        """
        # response_mime_type="application/json" for raw JSON as Gemini's output.
        # response_schema=GeminiAnalysis constrains Gemini to match the predefined Pydantic model.
        response = await self.client.aio.models.generate_content(
            model = self.model,
            contents = prompt,
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema = GeminiAnalysis,
            ),
        )

        # model_validate_json() parses the JSON string and validates it against the Pydantic model
        return GeminiAnalysis.model_validate_json(response.text)