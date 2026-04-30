"""Tests for POST /api/stores/search."""

import pytest
from sqlalchemy.orm import Session

from app.models.store import Service, Store, StoreStatus, StoreType


def _make_store(db: Session, store_id: str, lat: float, lon: float, **kwargs) -> Store:
    svc_lookup = {s.name: s for s in db.query(Service).all()}
    defaults = dict(
        name=f"Store {store_id}",
        store_type=StoreType.REGULAR,
        status=StoreStatus.ACTIVE,
        latitude=lat,
        longitude=lon,
        address_street="1 Main St",
        address_city="Boston",
        address_state="MA",
        address_postal_code="02101",
        address_country="USA",
        hours_mon="08:00-22:00",
        hours_tue="08:00-22:00",
        hours_wed="08:00-22:00",
        hours_thu="08:00-22:00",
        hours_fri="08:00-22:00",
        hours_sat="08:00-22:00",
        hours_sun="08:00-22:00",
    )
    defaults.update(kwargs)
    service_names = defaults.pop("services", [])
    store = Store(store_id=store_id, **defaults)
    store.services = [svc_lookup[n] for n in service_names if n in svc_lookup]
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


class TestSearchByCoordinates:
    def test_search_returns_nearby_store(self, client, seeded_roles, db_session):
        _make_store(db_session, "S0001", lat=42.3601, lon=-71.0589)
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589, "radius_miles": 5},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["results"][0]["store_id"] == "S0001"
        assert body["metadata"]["resolved_from"] == "coordinates"

    def test_search_excludes_store_beyond_radius(self, client, seeded_roles, db_session):
        _make_store(db_session, "S0001", lat=42.3601, lon=-71.0589)
        _make_store(db_session, "S0002", lat=43.0, lon=-71.0)  # ~46 miles away
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589, "radius_miles": 10},
        )
        assert r.status_code == 200
        ids = [s["store_id"] for s in r.json()["results"]]
        assert "S0001" in ids
        assert "S0002" not in ids

    def test_results_ordered_by_distance(self, client, seeded_roles, db_session):
        _make_store(db_session, "S0001", lat=42.3601, lon=-71.0589)  # origin
        _make_store(db_session, "S0002", lat=42.370, lon=-71.060)   # closer
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589, "radius_miles": 10},
        )
        ids = [s["store_id"] for s in r.json()["results"]]
        assert ids[0] == "S0001"  # distance 0 always first

    def test_inactive_store_excluded(self, client, seeded_roles, db_session):
        _make_store(db_session, "S0001", lat=42.3601, lon=-71.0589, status=StoreStatus.INACTIVE)
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589, "radius_miles": 5},
        )
        assert r.json()["count"] == 0


class TestSearchByPostalCode:
    def test_search_by_postal_code(self, client, seeded_roles, db_session):
        # conftest stub: "32801" → (28.5432, -81.3767)
        _make_store(db_session, "S0001", lat=28.5432, lon=-81.3767)
        r = client.post(
            "/api/stores/search",
            json={"postal_code": "32801", "radius_miles": 5},
        )
        assert r.status_code == 200
        assert r.json()["metadata"]["resolved_from"] == "postal_code"
        assert r.json()["count"] == 1

    def test_unknown_postal_code_returns_400(self, client, seeded_roles, db_session):
        # The mock geocoder returns None for queries containing "bogus" or "asdfgh"
        r = client.post(
            "/api/stores/search",
            json={"postal_code": "bogus asdfgh", "radius_miles": 5},
        )
        assert r.status_code == 400


class TestSearchByAddress:
    def test_search_by_address(self, client, seeded_roles, db_session):
        # conftest stub: "boston, ma" → (42.3601, -71.0589)
        _make_store(db_session, "S0001", lat=42.3601, lon=-71.0589)
        r = client.post(
            "/api/stores/search",
            json={"address": "Boston, MA", "radius_miles": 5},
        )
        assert r.status_code == 200
        assert r.json()["metadata"]["resolved_from"] == "address"

    def test_unknown_address_returns_400(self, client, seeded_roles, db_session):
        r = client.post(
            "/api/stores/search",
            json={"address": "bogus address asdfgh", "radius_miles": 5},
        )
        assert r.status_code == 400


class TestSearchFilters:
    def test_service_filter_and_logic(self, client, seeded_roles, db_session):
        _make_store(db_session, "S0001", lat=42.3601, lon=-71.0589,
                    services=["pharmacy", "pickup"])
        _make_store(db_session, "S0002", lat=42.3601, lon=-71.0589,
                    services=["pharmacy"])
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589,
                  "radius_miles": 5, "services": ["pharmacy", "pickup"]},
        )
        ids = [s["store_id"] for s in r.json()["results"]]
        assert "S0001" in ids
        assert "S0002" not in ids

    def test_store_type_filter(self, client, seeded_roles, db_session):
        _make_store(db_session, "S0001", lat=42.3601, lon=-71.0589,
                    store_type=StoreType.FLAGSHIP)
        _make_store(db_session, "S0002", lat=42.3601, lon=-71.0589,
                    store_type=StoreType.OUTLET)
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589,
                  "radius_miles": 5, "store_types": ["flagship"]},
        )
        ids = [s["store_id"] for s in r.json()["results"]]
        assert "S0001" in ids
        assert "S0002" not in ids

    def test_limit_respected(self, client, seeded_roles, db_session):
        for i in range(5):
            _make_store(db_session, f"S000{i}", lat=42.3601, lon=-71.0589)
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589,
                  "radius_miles": 5, "limit": 2},
        )
        assert len(r.json()["results"]) == 2


class TestSearchValidation:
    def test_missing_location_returns_422(self, client, seeded_roles):
        r = client.post("/api/stores/search", json={"radius_miles": 5})
        assert r.status_code == 422

    def test_multiple_locations_returns_422(self, client, seeded_roles):
        r = client.post(
            "/api/stores/search",
            json={"postal_code": "32801", "address": "Boston, MA", "radius_miles": 5},
        )
        assert r.status_code == 422

    def test_partial_coords_returns_422(self, client, seeded_roles):
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.0, "radius_miles": 5},
        )
        assert r.status_code == 422

    def test_unknown_service_returns_422(self, client, seeded_roles):
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.0, "longitude": -71.0,
                  "radius_miles": 5, "services": ["not_a_service"]},
        )
        assert r.status_code == 422
