from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "HealFlow AI"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/healflow"
    database_sync_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/healflow"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    jwt_secret_key: str = "change-me-in-production-use-a-real-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    encryption_key: str = "change-me-in-production-use-a-real-encryption-key-32bytes"

    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "healflow-backend"

    cors_origins: list[str] = ["http://localhost:3000"]

    # AI assistant — replies via the Claude API when a key is provided,
    # otherwise a built-in fallback responder keeps chat functional.
    ai_reply_enabled: bool = True
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    anthropic_max_tokens: int = 512


@lru_cache
def get_settings() -> Settings:
    return Settings()
