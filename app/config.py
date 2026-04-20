import os
from dotenv import load_dotenv

# Loading secrets from .env
load_dotenv()

class Settings:
    """
    Central configuration object.
    """

    GEMINI_API_KEY: str = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL: str = os.getenv('GEMINI_MODEL', 'gemini-flash-latest')
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    APP_ENV: str = os.getenv('APP_ENV', 'development')

settings = Settings()