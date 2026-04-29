"""Redis wrapper for geocoding + search-result caching.

Cache is best-effort — failures are swallowed and treated as cache misses
so a Redis outage degrades the app to "slow" instead of "broken".
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis
from redis.exceptions import RedisError

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def cache_get_json(key: str) -> Any:
    try:
        raw = get_redis().get(key)
    except RedisError as exc:
        logger.warning("Redis GET failed for %r: %s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Cache value for %r was not valid JSON; ignoring", key)
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        get_redis().set(key, json.dumps(value), ex=ttl_seconds)
    except RedisError as exc:
        logger.warning("Redis SET failed for %r: %s", key, exc)


def cache_delete(key: str) -> None:
    try:
        get_redis().delete(key)
    except RedisError as exc:
        logger.warning("Redis DEL failed for %r: %s", key, exc)


def ping() -> bool:
    try:
        return bool(get_redis().ping())
    except RedisError:
        return False
