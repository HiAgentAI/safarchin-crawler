import pytest
from app.core.config import Settings

def test_default_settings():
    settings = Settings()
    assert settings.PORT == 8000
    assert settings.API_KEY_PREFIX == "sc_"
    assert "postgresql+asyncpg://" in settings.async_database_url
    assert settings.REDIS_CACHE_TTL_SECONDS == 600

def test_custom_settings():
    settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        PORT=9000,
        DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/mydb",
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.DEBUG is False
    assert settings.PORT == 9000
    assert settings.async_database_url == "postgresql+asyncpg://user:pass@host:5432/mydb"
