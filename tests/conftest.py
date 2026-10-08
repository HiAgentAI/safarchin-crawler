import asyncio
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.db.base import Base
from app.api.deps import get_db, get_redis

# Test in-memory SQLite for super-fast, isolated testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session

class MockRedisClient:
    """Mock Redis client for testing caching and rate limiting."""
    def __init__(self):
        self._store = {}
        self._ttls = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex=None, **kwargs):
        # Accepts the ``ex``/``ttl`` expiry kwargs the real client supports, so
        # code under test can set an expiry without the double silently failing.
        self._store[key] = value
        if ex is not None:
            self._ttls[key] = ex
        elif kwargs.get("ex") is not None:
            self._ttls[key] = kwargs["ex"]
        return True

    async def setex(self, key: str, time: int, value: str):
        self._store[key] = value
        self._ttls[key] = time
        return True

    async def delete(self, *keys: str):
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
        return count

    async def exists(self, *keys: str):
        return sum(1 for k in keys if k in self._store)

    async def incr(self, key: str):
        val = int(self._store.get(key, 0)) + 1
        self._store[key] = str(val)
        return val

    async def expire(self, key: str, time: int):
        self._ttls[key] = time
        return True

    async def keys(self, pattern: str = "*"):
        return list(self._store.keys())

    async def flushdb(self):
        self._store.clear()
        self._ttls.clear()
        return True

    async def ping(self):
        return True

    async def info(self, section: str = "default"):
        return {
            "used_memory_human": "1.2M",
            "connected_clients": 1,
            "total_keys": len(self._store),
        }

@pytest.fixture
def mock_redis():
    return MockRedisClient()

@pytest_asyncio.fixture
async def async_client(db_session, mock_redis) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    async def override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
