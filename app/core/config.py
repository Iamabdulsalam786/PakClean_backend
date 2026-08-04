"""
Application settings loaded from environment variables / .env file.

Interview talking point:
  Config is centralized, typed, and validated at startup — fail fast if
  DATABASE_URL or SECRET_KEY is missing instead of crashing mid-request.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Single source of truth for runtime configuration.

    BaseSettings reads (in order of priority):
      1. Real OS environment variables
      2. Values from a .env file (if present)
      3. Field defaults defined below
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = Field(default="Pak Clean API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    # --- Server ---
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # --- Database ---
    database_url: str = Field(..., alias="DATABASE_URL")

    # --- Security / JWT ---
    secret_key: str = Field(..., alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(
        default=30,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        alias="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    algorithm: str = Field(default="HS256", alias="ALGORITHM")

    # --- Email / SMTP (Gmail App Password in development) ---
    # Optional at startup so the API can boot before mail is configured.
    # SmtpEmailSender wiring must still validate these before sending.
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    email_from: str = Field(default="", alias="EMAIL_FROM")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    # OTP policy (centralized so services don't hardcode magic numbers)
    otp_expire_minutes: int = Field(default=5, alias="OTP_EXPIRE_MINUTES")
    otp_resend_cooldown_seconds: int = Field(
        default=60,
        alias="OTP_RESEND_COOLDOWN_SECONDS",
    )
    otp_max_attempts: int = Field(default=5, alias="OTP_MAX_ATTEMPTS")

    # --- CORS ---
    # Stored as a raw comma-separated string in .env; exposed as a list via property.
    cors_origins_raw: str = Field(
        default="http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        """Keep environment names consistent (Development -> development)."""
        return value.strip().lower()

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """
        Render/Heroku often provide postgres:// or postgresql://.
        SQLAlchemy + psycopg v3 needs postgresql+psycopg://
        """
        url = value.strip()
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS_ORIGINS into a list FastAPI's CORSMiddleware expects."""
        return [
            origin.strip()
            for origin in self.cors_origins_raw.split(",")
            if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        """Helper so routes/middleware can branch without stringly-typed checks everywhere."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Build Settings once per process and reuse it.

    Why cache?
      - Reading/parsing env on every request is wasteful.
      - FastAPI Depends(get_settings) stays testable: clear cache + set env in tests.
    """
    return Settings()


# Convenience import for modules that do not need Depends():
#   from app.core.config import settings
settings = get_settings()
