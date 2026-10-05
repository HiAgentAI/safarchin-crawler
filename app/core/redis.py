import json
import logging
from typing import Optional, Any
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None

def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=5.0,
        )
    return _redis_client
 
def resolve_cache_params(
    no_cache: bool = False,
    cache_ttl: Optional[int] = None,
    cache_time: Optional[int] = None,
    default_ttl: int = 600,
) -> tuple[bool, int]:
    """
    Determine whether to use cache and the effective TTL in seconds.
    - If no_cache is True, caching is disabled (use_cache=False).
    - If caller provided cache_ttl or cache_time:
        - If <= 0, caching is disabled (use_cache=False).
        - If > 0, caching is enabled with that TTL.
    - If neither is provided, defaults to use_cache=True and default_ttl.
    """
    effective_ttl = cache_ttl if cache_ttl is not None else cache_time
    if no_cache:
        return False, 0
    if effective_ttl is not None:
        if effective_ttl <= 0:
            return False, 0
        return True, effective_ttl
    return True, default_ttl

class CacheManager:
    """Manages crawler result caching and deduplication."""
    def __init__(self, client: Optional[redis.Redis] = None):
        self.client = client or get_redis_client()

    async def get_json(self, key: str) -> Optional[Any]:
        try:
            val = await self.client.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.warning(f"Redis get failed for key {key}: {e}")
        return None

    async def set_json(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        try:
            ttl = ttl_seconds or settings.REDIS_CACHE_TTL_SECONDS
            await self.client.setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.warning(f"Redis set failed for key {key}: {e}")
            return False

    async def delete(self, *keys: str) -> int:
        try:
            return await self.client.delete(*keys)
        except Exception as e:
            logger.warning(f"Redis delete failed: {e}")
            return 0

    async def flush_all(self) -> bool:
        try:
            await self.client.flushdb()
            return True
        except Exception as e:
            logger.warning(f"Redis flush failed: {e}")
            return False

class RateLimiter:
    """Sliding minute-bucket rate limiter per API key."""
    def __init__(self, client: Optional[redis.Redis] = None):
        self.client = client or get_redis_client()

    async def is_rate_limited(self, key_id: str, limit_per_minute: int) -> tuple[bool, int]:
        """
        Check if key has exceeded its limit.
        Returns:
            (is_limited, current_count)
        """
        bucket_key = f"ratelimit:{key_id}"
        try:
            current = await self.client.incr(bucket_key)
            if current == 1:
                await self.client.expire(bucket_key, 60)
            if current > limit_per_minute:
                return True, current
            return False, current
        except Exception as e:
            logger.error(f"Rate limiting check failed: {e}")
            return False, 0
