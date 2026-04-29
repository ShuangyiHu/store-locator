"""Address / postal-code geocoding via Nominatim, with Redis caching.

Nominatim policy:
- Max 1 request/second (single thread)
- Must set a unique User-Agent identifying the app + contact
- Aggressive caching is expected for any non-trivial usage
"""

from __future__ import annotations

import logging

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from app.config import get_settings
from app.core.cache import cache_get_json, cache_set_json

logger = logging.getLogger(__name__)

_geolocator: Nominatim | None = None


def _get_geolocator() -> Nominatim:
    global _geolocator
    if _geolocator is None:
        settings = get_settings()
        _geolocator = Nominatim(user_agent=settings.nominatim_user_agent, timeout=10)
    return _geolocator


def _normalize(query: str) -> str:
    return " ".join(query.lower().strip().split())


def _cache_key(query: str) -> str:
    return f"geo:{_normalize(query)}"


def geocode(query: str) -> tuple[float, float] | None:
    """Resolve an address or postal code to (lat, lon).

    Returns None on not-found or upstream error. Both positive and negative
    results are cached for `geocoding_cache_ttl_seconds`.
    """
    if not query or not query.strip():
        return None

    settings = get_settings()
    key = _cache_key(query)

    cached = cache_get_json(key)
    if cached is not None:
        # Negative cache marker: {"lat": null}
        if cached.get("lat") is None:
            return None
        return (cached["lat"], cached["lon"])

    try:
        location = _get_geolocator().geocode(
            query,
            country_codes="us",
            exactly_one=True,
        )
    except (GeocoderServiceError, GeocoderTimedOut) as exc:
        logger.warning("Nominatim error for %r: %s", query, exc)
        return None

    if location is None:
        cache_set_json(
            key,
            {"lat": None, "lon": None},
            settings.geocoding_cache_ttl_seconds,
        )
        return None

    result = (float(location.latitude), float(location.longitude))
    cache_set_json(
        key,
        {"lat": result[0], "lon": result[1]},
        settings.geocoding_cache_ttl_seconds,
    )
    return result
