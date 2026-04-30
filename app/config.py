import os
from dotenv import load_dotenv

# Loading secrets from .env
load_dotenv()

class Settings:
    """
    Central configuration object.
    """

    # primary LLM provider
    GEMINI_API_KEY: str = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL: str = os.getenv('GEMINI_MODEL', 'gemini-flash-latest')
    # fallback LLM provider
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL: str = os.getenv('OPENAI_MODEL', 'gpt-5.4-mini')

    # rate limiting
    RATE_LIMIT: str = os.getenv('RATE_LIMIT', '5/minute')

    # app
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    APP_ENV: str = os.getenv('APP_ENV', 'development')

settings = Settings()