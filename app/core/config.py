from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment & Server
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    APP_PORT: Optional[int] = None
    HOST: str = "0.0.0.0"
    APP_HOST: Optional[str] = None

    @model_validator(mode="after")
    def resolve_server_ports(self):
        if self.APP_PORT is not None:
            self.PORT = self.APP_PORT
        if self.APP_HOST is not None:
            self.HOST = self.APP_HOST
        return self

    # PostgreSQL
    POSTGRES_USER: str = "safarchin"
    POSTGRES_PASSWORD: str = "safarchin_secret"
    POSTGRES_DB: str = "safarchin_crawler"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: Optional[str] = None

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL_SECONDS: int = 600

    # Security
    SECRET_KEY: str = "dev_secret_key_safarchin_2026"
    API_KEY_PREFIX: str = "sc_"
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 60
    DEFAULT_DAILY_QUOTA: int = 1000

    # Fuel stations (OpenStreetMap corridor search)
    # The public OSRM demo endpoint works for verification but carries no
    # availability guarantee, so production should point this at a self-hosted
    # or contracted instance.
    OSRM_BASE_URL: str = "https://router.project-osrm.org"
    NOMINATIM_URL: str = "https://nominatim.openstreetmap.org/search"
    FUEL_CORRIDOR_RADIUS_M: int = 1000
    FUEL_CORRIDOR_MAX_RADIUS_M: int = 10000
    FUEL_ROUTE_CACHE_TTL_SECONDS: int = 86400

    # Crawlers
    CRAWLER_DEFAULT_TIMEOUT: float = 15.0
    CRAWLER_MAX_CONCURRENCY: int = 5
    USER_AGENT_MODE: str = "desktop"

    # Provider Tokens
    JAJIGA_TOKEN: Optional[str] = None

settings = Settings()
