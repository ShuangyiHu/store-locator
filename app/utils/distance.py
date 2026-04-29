"""Bounding box pre-filter + haversine distance.

Approach: pre-filter candidates with a SQL BETWEEN clause on a degree-based
bounding box (cheap, uses the (lat, lon) composite index), then compute exact
geodesic distance in Python only for the small candidate set.
"""

from __future__ import annotations

from math import cos, radians

from geopy.distance import geodesic

# 1 degree of latitude ≈ 69.0 statute miles (constant).
# 1 degree of longitude varies with latitude — use cos(lat) correction.
_MILES_PER_LAT_DEGREE = 69.0


def bounding_box(
    lat: float, lon: float, radius_miles: float
) -> tuple[float, float, float, float]:
    """Return (min_lat, max_lat, min_lon, max_lon) enclosing the search circle.

    The box is conservative — slightly larger than the actual circle, so
    haversine post-filtering is required for an exact `distance <= radius`.
    """
    lat_delta = radius_miles / _MILES_PER_LAT_DEGREE
    # Avoid div-by-zero at the poles; clamp cos to a small positive value.
    cos_lat = max(cos(radians(lat)), 1e-6)
    lon_delta = radius_miles / (_MILES_PER_LAT_DEGREE * cos_lat)
    return (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Geodesic distance in miles. Uses geopy's WGS-84 ellipsoid model."""
    return geodesic((lat1, lon1), (lat2, lon2)).miles
