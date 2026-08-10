import time
from collections import defaultdict
from typing import Protocol

from redis.asyncio import Redis

from app.core.config import get_settings


class RateLimitExceeded(Exception):
    pass


class RateLimiterBackend(Protocol):
    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Return True if request is allowed, False if rate limited."""


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        window_start = now - window_seconds
        hits = [t for t in self._buckets[key] if t >= window_start]
        if len(hits) >= limit:
            self._buckets[key] = hits
            return False
        hits.append(now)
        self._buckets[key] = hits
        return True


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        client: Redis[str] | None = None
        try:
            client = Redis.from_url(self._redis_url, decode_responses=True)
            bucket_key = f"rl:{key}"
            count = await client.incr(bucket_key)
            if count == 1:
                await client.expire(bucket_key, window_seconds)
            return count <= limit
        finally:
            if client is not None:
                await client.close()


_limiter: RateLimiterBackend | None = None


def get_rate_limiter() -> RateLimiterBackend:
    global _limiter
    if _limiter is not None:
        return _limiter
    settings = get_settings()
    _limiter = RedisRateLimiter(settings.redis_url) if settings.redis_url else InMemoryRateLimiter()
    return _limiter


def reset_rate_limiter_for_tests() -> None:
    global _limiter
    _limiter = InMemoryRateLimiter()


async def enforce_rate_limit(*, key: str, limit: int, window_seconds: int = 60) -> None:
    allowed = await get_rate_limiter().hit(key, limit, window_seconds)
    if not allowed:
        raise RateLimitExceeded(key)
