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


#: Atomic fixed-window: set the TTL in the same round trip that creates the key.
#: The old two-step (INCR then, if first, EXPIRE) could leave a key with no TTL
#: if the process died between the calls — permanently rate-limiting that key.
#: `SET .. EX .. NX` seeds the window+TTL together; the INCR then counts.
_WINDOW_LUA = """
if redis.call('set', KEYS[1], 0, 'EX', ARGV[1], 'NX') then end
return redis.call('incr', KEYS[1])
"""


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        # One pooled client reused across hits, not a fresh connect+close per
        # request: under auth load the per-hit churn was latency and a risk of
        # exhausting Redis connections.
        self._redis: Redis[str] = Redis.from_url(redis_url, decode_responses=True)

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        count = await self._redis.eval(  # type: ignore[no-untyped-call]
            _WINDOW_LUA, 1, f"rl:{key}", window_seconds
        )
        return int(count) <= limit


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
