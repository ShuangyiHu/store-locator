from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Store Locator API"
    debug: bool = False
    environment: str = "development"

    database_url: str

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    nominatim_user_agent: str
    geocoding_cache_ttl_seconds: int = 60 * 60 * 24 * 30

    rate_limit_per_hour: int = 100
    rate_limit_per_minute: int = 10
    rate_limit_enabled: bool = True

    search_cache_ttl_seconds: int = 300
    default_radius_miles: float = 10.0
    max_radius_miles: float = 100.0

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
