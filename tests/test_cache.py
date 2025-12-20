import asyncio
from typing import Any

import pytest
from nthlayer.cache import RedisCache


class StubRedisClient:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def eval(
        self, script: str, numkeys: int, key: str, window_seconds: Any, max_requests: Any
    ) -> int:
        async with self._lock:
            current = self.counts.get(key)
            if current is None:
                self.counts[key] = 1
                return 1
            if current >= int(max_requests):
                return 0
            self.counts[key] = current + 1
            return 1


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_threshold() -> None:
    cache = RedisCache("redis://test", redis_client=StubRedisClient())

    assert await cache.rate_limit_check("rl:key", 2, 60)
    assert await cache.rate_limit_check("rl:key", 2, 60)
    assert not await cache.rate_limit_check("rl:key", 2, 60)


@pytest.mark.asyncio
async def test_rate_limit_is_atomic_under_concurrency() -> None:
    cache = RedisCache("redis://test", redis_client=StubRedisClient())

    results = await asyncio.gather(
        *[cache.rate_limit_check("rl:concurrent", 3, 60) for _ in range(6)]
    )

    assert sum(results) == 3
