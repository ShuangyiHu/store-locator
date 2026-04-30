"""Tests for /api/admin/stores endpoints (CRUD + permissions)."""

import pytest
from sqlalchemy.orm import Session

from app.models.store import Service, Store, StoreStatus, StoreType

_VALID_STORE = {
    "store_id": "S0001",
    "name": "Test Store",
    "store_type": "regular",
    "status": "active",
    "latitude": 42.3601,
    "longitude": -71.0589,
    "address_street": "1 Main St",
    "address_city": "Boston",
    "address_state": "MA",
    "address_postal_code": "02101",
    "address_country": "USA",
    "phone": "617-555-1234",
    "services": [],
    "hours_mon": "08:00-22:00",
    "hours_tue": "08:00-22:00",
    "hours_wed": "08:00-22:00",
    "hours_thu": "08:00-22:00",
    "hours_fri": "08:00-22:00",
    "hours_sat": "closed",
    "hours_sun": "10:00-20:00",
}


class TestCreateStore:
    def test_admin_can_create_store(self, client, admin_headers):
        r = client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        assert r.status_code == 201
        body = r.json()
        assert body["store_id"] == "S0001"
        assert body["name"] == "Test Store"

    def test_marketer_can_create_store(self, client, marketer_headers):
        r = client.post("/api/admin/stores", json=_VALID_STORE, headers=marketer_headers)
        assert r.status_code == 201

    def test_viewer_cannot_create_store(self, client, viewer_headers):
        r = client.post("/api/admin/stores", json=_VALID_STORE, headers=viewer_headers)
        assert r.status_code == 403

    def test_unauthenticated_cannot_create_store(self, client, seeded_users):
        r = client.post("/api/admin/stores", json=_VALID_STORE)
        assert r.status_code == 401

    def test_duplicate_store_id_returns_409(self, client, admin_headers):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        r = client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        assert r.status_code == 409

    def test_invalid_store_id_format_returns_422(self, client, admin_headers):
        payload = {**_VALID_STORE, "store_id": "INVALID"}
        r = client.post("/api/admin/stores", json=payload, headers=admin_headers)
        assert r.status_code == 422

    def test_invalid_phone_returns_422(self, client, admin_headers):
        payload = {**_VALID_STORE, "phone": "not-a-phone"}
        r = client.post("/api/admin/stores", json=payload, headers=admin_headers)
        assert r.status_code == 422

    def test_invalid_store_type_returns_422(self, client, admin_headers):
        payload = {**_VALID_STORE, "store_type": "superstore"}
        r = client.post("/api/admin/stores", json=payload, headers=admin_headers)
        assert r.status_code == 422

    def test_geocode_used_when_coords_omitted(self, client, admin_headers):
        payload = {k: v for k, v in _VALID_STORE.items()
                   if k not in ("latitude", "longitude")}
        r = client.post("/api/admin/stores", json=payload, headers=admin_headers)
        assert r.status_code == 201
        body = r.json()
        assert body["latitude"] is not None
        assert body["longitude"] is not None


class TestListStores:
    def test_admin_can_list_stores(self, client, admin_headers):
        r = client.get("/api/admin/stores", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body

    def test_viewer_can_list_stores(self, client, viewer_headers):
        r = client.get("/api/admin/stores", headers=viewer_headers)
        assert r.status_code == 200

    def test_unauthenticated_cannot_list_stores(self, client, seeded_users):
        r = client.get("/api/admin/stores")
        assert r.status_code == 401

    def test_pagination(self, client, admin_headers):
        for i in range(1, 6):
            payload = {**_VALID_STORE, "store_id": f"S{i:04d}"}
            client.post("/api/admin/stores", json=payload, headers=admin_headers)
        r = client.get("/api/admin/stores?page=1&page_size=3", headers=admin_headers)
        body = r.json()
        assert body["total"] == 5
        assert len(body["items"]) == 3

    def test_status_filter(self, client, admin_headers):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        r = client.get("/api/admin/stores?status=active", headers=admin_headers)
        assert r.status_code == 200
        assert all(item["status"] == "active" for item in r.json()["items"])

    def test_invalid_status_filter_returns_400(self, client, admin_headers):
        r = client.get("/api/admin/stores?status=nonexistent", headers=admin_headers)
        assert r.status_code == 400


class TestGetStore:
    def test_get_existing_store(self, client, admin_headers):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        r = client.get("/api/admin/stores/S0001", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["store_id"] == "S0001"

    def test_get_nonexistent_store_returns_404(self, client, admin_headers):
        r = client.get("/api/admin/stores/S9999", headers=admin_headers)
        assert r.status_code == 404

    def test_unauthenticated_cannot_get_store(self, client, admin_headers, seeded_users):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        r = client.get("/api/admin/stores/S0001")
        assert r.status_code == 401


class TestUpdateStore:
    def test_admin_can_update_name(self, client, admin_headers):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        r = client.patch(
            "/api/admin/stores/S0001",
            json={"name": "Updated Name"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Updated Name"

    def test_update_nonexistent_store_returns_404(self, client, admin_headers):
        r = client.patch(
            "/api/admin/stores/S9999",
            json={"name": "Doesn't Matter"},
            headers=admin_headers,
        )
        assert r.status_code == 404

    def test_viewer_cannot_update_store(self, client, viewer_headers, admin_headers):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        r = client.patch(
            "/api/admin/stores/S0001",
            json={"name": "Hacked"},
            headers=viewer_headers,
        )
        assert r.status_code == 403

    def test_cannot_patch_immutable_fields(self, client, admin_headers):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        r = client.patch(
            "/api/admin/stores/S0001",
            json={"store_id": "S9999"},
            headers=admin_headers,
        )
        assert r.status_code == 422


class TestDeactivateStore:
    def test_admin_can_deactivate_store(self, client, admin_headers):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        r = client.delete("/api/admin/stores/S0001", headers=admin_headers)
        assert r.status_code == 204

    def test_delete_sets_status_to_inactive(self, client, admin_headers):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        client.delete("/api/admin/stores/S0001", headers=admin_headers)
        r = client.get("/api/admin/stores/S0001", headers=admin_headers)
        assert r.json()["status"] == "inactive"

    def test_delete_nonexistent_store_returns_404(self, client, admin_headers):
        r = client.delete("/api/admin/stores/S9999", headers=admin_headers)
        assert r.status_code == 404

    def test_viewer_cannot_delete_store(self, client, viewer_headers, admin_headers):
        client.post("/api/admin/stores", json=_VALID_STORE, headers=admin_headers)
        r = client.delete("/api/admin/stores/S0001", headers=viewer_headers)
        assert r.status_code == 403
