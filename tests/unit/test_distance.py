import pytest

from app.utils.distance import bounding_box, haversine_miles


class TestBoundingBox:
    def test_box_around_boston_is_symmetric_in_lat(self):
        lat, lon = 42.3601, -71.0589
        radius = 10.0
        mn_lat, mx_lat, mn_lon, mx_lon = bounding_box(lat, lon, radius)
        # lat delta = radius / 69 ≈ 0.1449
        assert mn_lat == pytest.approx(lat - radius / 69.0, abs=1e-6)
        assert mx_lat == pytest.approx(lat + radius / 69.0, abs=1e-6)

    def test_box_lon_delta_widens_with_latitude_via_cos_correction(self):
        # Same radius, two latitudes: equator delta ≈ pole-ish delta * cos
        eq_box = bounding_box(0.0, 0.0, 10.0)
        far_north_box = bounding_box(60.0, 0.0, 10.0)
        eq_lon_delta = eq_box[3] - eq_box[2]
        north_lon_delta = far_north_box[3] - far_north_box[2]
        # cos(60°) = 0.5, so northern delta should be ~2x equatorial
        assert north_lon_delta == pytest.approx(eq_lon_delta * 2, rel=0.01)

    def test_box_does_not_blow_up_at_pole(self):
        # cos(90°) = 0 → division would explode without the clamp
        box = bounding_box(90.0, 0.0, 10.0)
        assert all(isinstance(x, float) for x in box)


class TestHaversine:
    def test_zero_distance_to_self(self):
        assert haversine_miles(42.0, -71.0, 42.0, -71.0) == pytest.approx(0.0, abs=1e-6)

    def test_known_pair_boston_to_cambridge(self):
        # ~2.7 miles
        d = haversine_miles(42.3601, -71.0589, 42.3736, -71.1097)
        assert 2.5 < d < 3.0

    def test_known_pair_nyc_to_la(self):
        # ~2451 miles great-circle
        d = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)
        assert 2400 < d < 2500
