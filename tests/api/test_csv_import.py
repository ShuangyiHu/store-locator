"""Tests for POST /api/admin/stores/import (CSV bulk upload)."""

import io


HEADER = (
    "store_id,name,store_type,status,latitude,longitude,"
    "address_street,address_city,address_state,address_postal_code,address_country,"
    "phone,services,"
    "hours_mon,hours_tue,hours_wed,hours_thu,hours_fri,hours_sat,hours_sun"
)

_GOOD_ROW = (
    "S0001,Test Store,regular,active,42.3601,-71.0589,"
    "1 Main St,Boston,MA,02101,USA,"
    "617-555-1234,pharmacy|pickup,"
    "08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00,closed,10:00-20:00"
)


def _csv(*rows: str) -> bytes:
    return "\n".join([HEADER, *rows]).encode()


class TestCSVImportSuccess:
    def test_import_single_row(self, client, admin_headers):
        data = _csv(_GOOD_ROW)
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(data), "text/csv")},
            headers=admin_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["created"] == 1
        assert body["updated"] == 0
        assert body["failed"] == 0

    def test_import_multiple_rows(self, client, admin_headers):
        row2 = _GOOD_ROW.replace("S0001", "S0002")
        data = _csv(_GOOD_ROW, row2)
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(data), "text/csv")},
            headers=admin_headers,
        )
        body = r.json()
        assert body["success"] is True
        assert body["created"] == 2

    def test_import_updates_existing_store(self, client, admin_headers):
        client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(_csv(_GOOD_ROW)), "text/csv")},
            headers=admin_headers,
        )
        updated_row = _GOOD_ROW.replace("Test Store", "Updated Store")
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(_csv(updated_row)), "text/csv")},
            headers=admin_headers,
        )
        body = r.json()
        assert body["success"] is True
        assert body["created"] == 0
        assert body["updated"] == 1

    def test_geocode_used_when_coords_empty(self, client, admin_headers):
        # Replace "42.3601,-71.0589" with "," to leave both lat and lon empty
        row_no_coords = _GOOD_ROW.replace("42.3601,-71.0589", ",")
        data = _csv(row_no_coords)
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(data), "text/csv")},
            headers=admin_headers,
        )
        assert r.json()["success"] is True


class TestCSVImportValidation:
    def test_wrong_extension_returns_400(self, client, admin_headers):
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.txt", io.BytesIO(b"data"), "text/plain")},
            headers=admin_headers,
        )
        assert r.status_code == 400

    def test_wrong_headers_returns_400(self, client, admin_headers):
        bad_csv = b"col1,col2\nval1,val2\n"
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(bad_csv), "text/csv")},
            headers=admin_headers,
        )
        assert r.status_code == 400

    def test_row_validation_errors_returned(self, client, admin_headers):
        bad_row = _GOOD_ROW.replace("S0001", "INVALID").replace("regular", "superstore")
        data = _csv(bad_row)
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(data), "text/csv")},
            headers=admin_headers,
        )
        body = r.json()
        assert body["success"] is False
        assert body["failed"] >= 1
        assert len(body["errors"]) >= 1

    def test_geocode_failure_returns_error(self, client, admin_headers):
        row_bogus = (
            "S0002,Bogus Store,regular,active,,,,"
            "bogus address,,MA,02101,USA,"
            ",,"
            "08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00,closed,10:00-20:00"
        )
        # This row has mangled structure; easier to test via a known unfindable address
        row_no_coords = _GOOD_ROW.replace(",42.3601,-71.0589,", ",,").replace(
            "1 Main St,Boston", "bogus asdfgh,Somewhere"
        )
        data = _csv(row_no_coords)
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(data), "text/csv")},
            headers=admin_headers,
        )
        body = r.json()
        assert body["success"] is False


class TestCSVImportPermissions:
    def test_marketer_can_import(self, client, marketer_headers):
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(_csv(_GOOD_ROW)), "text/csv")},
            headers=marketer_headers,
        )
        assert r.status_code == 200

    def test_viewer_cannot_import(self, client, viewer_headers):
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(_csv(_GOOD_ROW)), "text/csv")},
            headers=viewer_headers,
        )
        assert r.status_code == 403

    def test_unauthenticated_cannot_import(self, client, seeded_users):
        r = client.post(
            "/api/admin/stores/import",
            files={"file": ("stores.csv", io.BytesIO(_csv(_GOOD_ROW)), "text/csv")},
        )
        assert r.status_code == 401
