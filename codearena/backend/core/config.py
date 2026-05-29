"""
Configuration — loads from environment variables / .env file
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Grok / xAI
    GROK_API_KEY: str = "your-grok-api-key-here"
    GROK_MODEL: str = "grok-3"                         # or "grok-3-mini" for speed
    GROK_BASE_URL: str = "https://api.x.ai/v1"

    # App
    SECRET_KEY: str = "change-this-in-production"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Sandbox limits
    EXECUTION_TIMEOUT_SECS: int = 10
    EXECUTION_MEMORY_MB: int = 256

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
