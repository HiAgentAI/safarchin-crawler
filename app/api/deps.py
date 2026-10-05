from typing import AsyncGenerator, Optional
import json
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_maker
from app.db.models import APIKey
from app.core.security import hash_api_key
from app.core.redis import get_redis_client, RateLimiter

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

async def get_redis():
    return get_redis_client()

async def verify_api_key(
    api_key_header: Optional[str] = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
    redis_client = Depends(get_redis),
) -> APIKey:
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'X-API-Key' header",
        )

    key_hash = hash_api_key(api_key_header)
    redis_cache_key = f"auth_key:{key_hash}"

    # Fast path: check Redis auth cache
    cached_info = await redis_client.get(redis_cache_key)
    if cached_info:
        data = json.loads(cached_info)
        if not data.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API Key is inactive or revoked",
            )
        key_id = data["id"]
        rate_limit = data.get("rate_limit_per_min", 60)
        # Check rate limiter
        limiter = RateLimiter(redis_client)
        is_limited, current = await limiter.is_rate_limited(key_id, rate_limit)
        if is_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({rate_limit} requests/min)",
            )
        # Create lightweight APIKey object from cache
        key = APIKey(
            id=data["id"],
            key_hash=key_hash,
            client_name=data["client_name"],
            tier=data["tier"],
            rate_limit_per_min=rate_limit,
            daily_quota=data.get("daily_quota", 1000),
            is_active=True,
        )
        return key

    # Slow path: query DB
    result = await db.execute(select(APIKey).where(APIKey.key_hash == key_hash))
    key = result.scalar_one_or_none()

    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    if not key.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key is inactive or revoked",
        )

    # Cache key metadata in Redis for 5 minutes
    key_data = {
        "id": key.id,
        "client_name": key.client_name,
        "tier": key.tier,
        "rate_limit_per_min": key.rate_limit_per_min,
        "daily_quota": key.daily_quota,
        "is_active": key.is_active,
    }
    await redis_client.setex(redis_cache_key, 300, json.dumps(key_data))

    # Check rate limiter
    limiter = RateLimiter(redis_client)
    is_limited, current = await limiter.is_rate_limited(key.id, key.rate_limit_per_min)
    if is_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded ({key.rate_limit_per_min} requests/min)",
        )

    return key
