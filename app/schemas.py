from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

class SentimentLabel(str, Enum):
    """
    Using str + Enum means the value serializes as a plain string in JSON ("positive") instead of {"value": "positive"}.
    FastAPI handles this automatically in the response.
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    NEUTRAL = "neutral"

class GeminiAnalysis(BaseModel):
    """
    This model does double duty:
    1. Passed to Gemini as 'response_schema' - The API uses it to constrain its output to valid JSON matching this
    exact shape. No post-processing.
    2. Used to parse and validate the response with model_validate_json().
    """

    overall_sentiment: SentimentLabel
    sentiment_score: float = Field(
        ...,
        ge = -1.0,
        le = 1.0,
        description = "Sentiment polarity: -1.0 = very negative, 1.0 = very positive",
    )
    themes: List[str] = Field(
        ...,
        description = "Main topics and themes mentioned across reviews",
    )
    pain_points: List[str] = Field(
        ...,
        description = "Specific problems and frustrations mentioned by customers/users",
    )
    feature_requests: List[str] = Field(
        ...,
        description = "Features or improvements asked by customers/users",
    )
    summary: str = Field(
        ...,
        description = "2-3 sentence plain-English summary of the overall analysis",
    )

class ReviewRequest(BaseModel):
    """
    JSON body that the client sends. FastAPI automatically validates this against the incoming request body before
    the handler even runs. A 422 Unprocessable Entity is returned if validation fails.
    """

    reviews: List[str] = Field(
        ...,
        min_length = 1,
        description = "List of customer review texts to analyze",
    )
    product_name: Optional[str] = Field(
        None,
        description = "Optional product name to add context to the LLM prompt",
    )

class ReviewResponse(BaseModel):
    """
    What the API returns to the client. Wraps GeminiAnalysis with metadata added after the llm response (review_count,
    model_used).
    """

    product_name: Optional[str]
    review_count: int
    model_used: str
    analysis: GeminiAnalysis