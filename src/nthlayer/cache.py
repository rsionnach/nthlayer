from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger()

_RATE_LIMIT_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then
    redis.call('SET', KEYS[1], 1, 'EX', ARGV[1])
    return 1
end
if tonumber(current) >= tonumber(ARGV[2]) then
    return 0
end
redis.call('INCR', KEYS[1])
return 1
"""


class RedisCache:
    """Redis-based caching and rate limiting."""

    def __init__(
        self,
        redis_url: str,
        max_connections: int = 50,
        redis_client: aioredis.Redis | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool: aioredis.ConnectionPool | None = None
        self._client: aioredis.Redis | None = redis_client

        if redis_client is None:
            self._pool = aioredis.ConnectionPool.from_url(
                redis_url,
                max_connections=max_connections,
                decode_responses=True,
            )

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.Redis(connection_pool=self._pool)
        return self._client

    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        client = await self._get_client()
        value = await client.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set value in cache with TTL in seconds."""
        client = await self._get_client()
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await client.setex(key, ttl, serialized)

    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        client = await self._get_client()
        await client.delete(key)

    async def rate_limit_check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> bool:
        """
        Check if rate limit is exceeded using token bucket algorithm.
        Returns True if request is allowed, False if rate limited.
        """
        client = await self._get_client()
        allowed = await client.eval(
            _RATE_LIMIT_SCRIPT,
            1,
            key,
            window_seconds,
            max_requests,
        )

        if not allowed:
            logger.warning("rate_limit_exceeded", key=key, max=max_requests)
        return bool(allowed)

    async def acquire_lock(self, key: str, ttl: int = 60) -> bool:
        """Acquire distributed lock. Returns True if lock acquired."""
        client = await self._get_client()
        return await client.set(key, "locked", nx=True, ex=ttl)

    async def release_lock(self, key: str) -> None:
        """Release distributed lock."""
        await self.delete(key)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
        if self._pool is not None:
            await self._pool.disconnect()
