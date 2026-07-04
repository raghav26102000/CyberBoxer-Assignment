"""
Minimal in-memory TTL cache for the two report endpoints.

Not Redis, not a caching library -- a plain dict with timestamps. That's
the right amount of complexity for a single-process take-home app. If
this ran across multiple processes/instances, a shared cache (Redis)
would be required since each process would otherwise have its own
inconsistent cache; that tradeoff is called out in the README.

Cache entries are invalidated immediately after a successful /upload,
so a cache hit can never return numbers from before the latest data.
"""
import time
from typing import Any, Callable
from app.config import REPORT_CACHE_TTL_SECONDS

_cache: dict[str, tuple[float, Any]] = {}


def get_or_set(key: str, compute: Callable[[], Any], ttl: int = REPORT_CACHE_TTL_SECONDS) -> Any:
    now = time.time()
    if key in _cache:
        expires_at, value = _cache[key]
        if now < expires_at:
            return value
    value = compute()
    _cache[key] = (now + ttl, value)
    return value


async def get_or_set_async(key: str, compute, ttl: int = REPORT_CACHE_TTL_SECONDS) -> Any:
    now = time.time()
    if key in _cache:
        expires_at, value = _cache[key]
        if now < expires_at:
            return value
    value = await compute()
    _cache[key] = (now + ttl, value)
    return value


def invalidate_all() -> None:
    _cache.clear()
