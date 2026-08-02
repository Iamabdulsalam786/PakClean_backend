from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Convert Render/Heroku postgres URLs to SQLAlchemy asyncpg format."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PakClean API"
    environment: str = "development"
    port: int = 8000
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://pakclean:pakclean@localhost:5432/pakclean"

    jwt_access_secret: str
    jwt_refresh_secret: str
    jwt_access_expires_minutes: int = 15
    jwt_refresh_expires_days: int = 30
    jwt_refresh_expires_days_short: int = 7

    otp_length: int = 6
    otp_expires_minutes: int = 10
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 30

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from: str = "PakClean <noreply@pakclean.com>"

    cors_origins: str = "*"

    @field_validator("database_url", mode="before")
    @classmethod
    def parse_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
