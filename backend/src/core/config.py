"""Application configuration loaded from environment variables."""

from typing import List, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for the backend application."""

    PROJECT_NAME: str = "Career Scout API"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="local", alias="ENV")
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/career_scout"
    )
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 3600
    DB_POOL_TIMEOUT: int = 30
    DB_CONNECT_RETRIES: int = 3
    DB_CONNECT_RETRY_DELAY: float = 1.0

    # CORS
    CORS_ORIGINS: List[str] = Field(default_factory=list)

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        """Normalize CORS origins from env variables.

        Args:
            value: Raw env value, list, or comma-separated string.

        Returns:
            List of CORS origins.

        Raises:
            ValueError: If the input cannot be parsed.
        """
        if value is None:
            return []
        if isinstance(value, str):
            if not value.strip():
                return []
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        raise ValueError("CORS_ORIGINS must be a list or comma-separated string")


settings = Settings()
