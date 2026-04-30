"""IP-based rate limiting on public endpoints.

Implementation: fixed-window counters in Redis, one per (ip, granularity).
Each window auto-expires (TTL = window length). Two windows are checked
per request: per-minute and per-hour.

We deliberately do NOT use slowapi's decorator here because it is known to
interfere with FastAPI's pydantic body-parameter inference when stacked on
sync routes. Implementing as a FastAPI dependency keeps route signatures
clean and gives us precise control over the 429 response/headers.
"""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.config import get_settings
from app.core.cache import get_redis

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    """Honor X-Forwarded-For when set by a trusted proxy; fall back to peer IP."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def _check_window(
    ip: str,
    granularity: str,
    window_seconds: int,
    limit: int,
) -> tuple[int, int]:
    """Increment the counter for this (ip, window). Returns (count, retry_after_sec).

    `count` is the post-increment count; if > limit, the request is over budget.
    `retry_after_sec` is how long until this window rolls over.
    """
    now = int(time.time())
    bucket = now // window_seconds
    key = f"ratelimit:{ip}:{granularity}:{bucket}"

    redis = get_redis()
    pipe = redis.pipeline()
    pipe.incr(key, 1)
    pipe.expire(key, window_seconds)
    count, _ = pipe.execute()

    next_bucket_starts_at = (bucket + 1) * window_seconds
    retry_after = max(1, next_bucket_starts_at - now)
    return int(count), retry_after


def public_rate_limit(request: Request) -> None:
    """FastAPI dependency: enforce per-minute + per-hour limits per IP.

    Fails open on Redis errors — better to over-serve than to lock everyone
    out when the cache is down. The Redis ping in /health makes outages
    observable.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    ip = _client_ip(request)

    try:
        m_count, m_retry = _check_window(ip, "m", 60, settings.rate_limit_per_minute)
        h_count, h_retry = _check_window(ip, "h", 3600, settings.rate_limit_per_hour)
    except RedisError as exc:
        logger.warning("Rate limiter Redis error (failing open): %s", exc)
        return

    if m_count > settings.rate_limit_per_minute:
        _raise_429("per-minute", settings.rate_limit_per_minute, m_count, m_retry)
    if h_count > settings.rate_limit_per_hour:
        _raise_429("per-hour", settings.rate_limit_per_hour, h_count, h_retry)


def _raise_429(window: str, limit: int, count: int, retry_after: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Rate limit exceeded ({window}: {count}/{limit})",
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + retry_after),
        },
    )
