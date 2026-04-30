"""End-to-end search flow: create stores → search with filters."""

import io


_HEADER = (
    "store_id,name,store_type,status,latitude,longitude,"
    "address_street,address_city,address_state,address_postal_code,address_country,"
    "phone,services,"
    "hours_mon,hours_tue,hours_wed,hours_thu,hours_fri,hours_sat,hours_sun"
)

_HOURS_OPEN = "08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00"
_HOURS_CLOSED = "closed,closed,closed,closed,closed,closed,closed"


def _row(store_id, name, lat, lon, services="", store_type="regular",
         status="active", hours=_HOURS_OPEN):
    return (
        f"{store_id},{name},{store_type},{status},{lat},{lon},"
        f"1 Main St,Boston,MA,02101,USA,"
        f"617-555-0000,{services},"
        f"{hours}"
    )


def _csv(*rows):
    return "\n".join([_HEADER, *rows]).encode()


def _import(client, headers, *rows):
    data = _csv(*rows)
    r = client.post(
        "/api/admin/stores/import",
        files={"file": ("stores.csv", io.BytesIO(data), "text/csv")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


class TestSearchAfterImport:
    def test_imported_store_appears_in_search(self, client, admin_headers):
        _import(client, admin_headers, _row("S0001", "Near Store", 42.3601, -71.0589))
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589, "radius_miles": 5},
        )
        assert r.status_code == 200
        ids = [s["store_id"] for s in r.json()["results"]]
        assert "S0001" in ids

    def test_search_respects_service_filter(self, client, admin_headers):
        _import(
            client, admin_headers,
            _row("S0001", "Pharmacy Store", 42.3601, -71.0589, services="pharmacy|pickup"),
            _row("S0002", "No Pharmacy", 42.3601, -71.0589, services="returns"),
        )
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589,
                  "radius_miles": 5, "services": ["pharmacy"]},
        )
        ids = [s["store_id"] for s in r.json()["results"]]
        assert "S0001" in ids
        assert "S0002" not in ids

    def test_deleted_store_excluded_from_search(self, client, admin_headers):
        _import(client, admin_headers, _row("S0001", "To Delete", 42.3601, -71.0589))
        client.delete("/api/admin/stores/S0001", headers=admin_headers)
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589, "radius_miles": 5},
        )
        ids = [s["store_id"] for s in r.json()["results"]]
        assert "S0001" not in ids

    def test_search_by_postal_code_returns_nearby(self, client, admin_headers):
        # conftest stub: "32801" → (28.5432, -81.3767)
        _import(client, admin_headers, _row("S0001", "Orlando Store", 28.5432, -81.3767))
        r = client.post(
            "/api/stores/search",
            json={"postal_code": "32801", "radius_miles": 5},
        )
        assert r.status_code == 200
        assert r.json()["count"] == 1

    def test_store_type_filter_applied(self, client, admin_headers):
        _import(
            client, admin_headers,
            _row("S0001", "Flagship", 42.3601, -71.0589, store_type="flagship"),
            _row("S0002", "Outlet", 42.3601, -71.0589, store_type="outlet"),
        )
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589,
                  "radius_miles": 5, "store_types": ["flagship"]},
        )
        ids = [s["store_id"] for s in r.json()["results"]]
        assert "S0001" in ids
        assert "S0002" not in ids

    def test_results_sorted_nearest_first(self, client, admin_headers):
        _import(
            client, admin_headers,
            _row("S0001", "Far Store", 42.40, -71.06),   # ~2.7 miles from origin
            _row("S0002", "Near Store", 42.361, -71.059), # ~0.1 mile from origin
        )
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589, "radius_miles": 10},
        )
        ids = [s["store_id"] for s in r.json()["results"]]
        assert ids.index("S0002") < ids.index("S0001")

    def test_unauthenticated_can_search(self, client, seeded_roles):
        # Public endpoint — no token required
        r = client.post(
            "/api/stores/search",
            json={"latitude": 42.3601, "longitude": -71.0589, "radius_miles": 5},
        )
        assert r.status_code == 200
