"""Application configuration loaded from environment variables and secrets files."""

from pathlib import Path
from typing import List, Union
from urllib.parse import quote_plus, urlsplit, urlunsplit

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
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "career-scout"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_PASSWORD_FILE: str = ""
    DATABASE_URL_OVERRIDE: str = Field(default="", alias="DATABASE_URL")
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
    def parse_cors_origins(
        cls, value: Union[str, List[str], tuple[str, ...], set[str], None]
    ) -> List[str]:
        """Normalize CORS origins from env variables.

        Args:
            value: Raw env value (None, list/tuple/set, or comma-separated string).

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

    @property
    def resolved_db_password(self) -> str:
        """Resolve database password from secrets file or environment.

        Returns:
            str: Password read from ``DB_PASSWORD_FILE`` when available,
            otherwise the ``DB_PASSWORD`` setting.
        """
        if self.DB_PASSWORD_FILE:
            try:
                password_file = Path(self.DB_PASSWORD_FILE)
                if password_file.is_file():
                    return password_file.read_text(encoding="utf-8").rstrip()
            except OSError:
                return self.DB_PASSWORD
        return self.DB_PASSWORD

    @property
    def DATABASE_URL(self) -> str:
        """Build the async SQLAlchemy database URL from DB_* fields.

        Returns:
            str: SQLAlchemy async PostgreSQL URL.

        Raises:
            ValueError: If the configured URL does not use PostgreSQL.
        """
        if self.DATABASE_URL_OVERRIDE:
            override = self.DATABASE_URL_OVERRIDE.strip()
            if override:
                return self._normalize_async_database_url(override)

        db_user = quote_plus(self.DB_USER)
        db_password = quote_plus(self.resolved_db_password)
        built_url = (
            f"postgresql+asyncpg://{db_user}:{db_password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
        return self._normalize_async_database_url(built_url)

    def _normalize_async_database_url(self, database_url: str) -> str:
        """Normalize PostgreSQL URL to SQLAlchemy asyncpg format.

        Args:
            database_url: Raw database connection URL.

        Returns:
            str: URL with ``postgresql+asyncpg`` scheme.

        Raises:
            ValueError: If the scheme is not PostgreSQL-compatible.
        """
        parsed_url = urlsplit(database_url)
        scheme = parsed_url.scheme.lower()

        if not (
            scheme in {"postgres", "postgresql"} or scheme.startswith("postgresql+")
        ):
            raise ValueError(
                "DATABASE_URL must use postgres/postgresql scheme for async SQLAlchemy"
            )

        return urlunsplit(
            (
                "postgresql+asyncpg",
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.query,
                parsed_url.fragment,
            )
        )


settings = Settings()
