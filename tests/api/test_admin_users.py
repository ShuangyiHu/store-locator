"""Tests for /api/admin/users endpoints."""


class TestCreateUser:
    def test_admin_can_create_user(self, client, admin_headers):
        r = client.post(
            "/api/admin/users",
            json={
                "email": "new@test.com",
                "password": "NewUser123!",
                "full_name": "New User",
                "role": "viewer",
            },
            headers=admin_headers,
        )
        assert r.status_code == 201
        body = r.json()
        assert body["email"] == "new@test.com"
        assert body["role"] == "viewer"

    def test_marketer_cannot_manage_users(self, client, marketer_headers):
        r = client.post(
            "/api/admin/users",
            json={
                "email": "new@test.com",
                "password": "NewUser123!",
                "full_name": "New User",
                "role": "viewer",
            },
            headers=marketer_headers,
        )
        assert r.status_code == 403

    def test_viewer_cannot_manage_users(self, client, viewer_headers):
        r = client.post(
            "/api/admin/users",
            json={
                "email": "new@test.com",
                "password": "NewUser123!",
                "full_name": "New User",
                "role": "viewer",
            },
            headers=viewer_headers,
        )
        assert r.status_code == 403

    def test_duplicate_email_returns_409(self, client, admin_headers, seeded_users):
        r = client.post(
            "/api/admin/users",
            json={
                "email": "viewer@test.com",
                "password": "SomePass123!",
                "role": "viewer",
            },
            headers=admin_headers,
        )
        assert r.status_code == 409

    def test_invalid_role_returns_422(self, client, admin_headers):
        r = client.post(
            "/api/admin/users",
            json={
                "email": "new@test.com",
                "password": "NewUser123!",
                "role": "superadmin",
            },
            headers=admin_headers,
        )
        assert r.status_code == 422

    def test_invalid_email_returns_422(self, client, admin_headers):
        r = client.post(
            "/api/admin/users",
            json={
                "email": "not-an-email",
                "password": "NewUser123!",
                "role": "viewer",
            },
            headers=admin_headers,
        )
        assert r.status_code == 422

    def test_unauthenticated_cannot_create_user(self, client, seeded_users):
        r = client.post(
            "/api/admin/users",
            json={"email": "new@test.com", "password": "Pass123!", "role": "viewer"},
        )
        assert r.status_code == 401


class TestListUsers:
    def test_admin_can_list_users(self, client, admin_headers, seeded_users):
        r = client.get("/api/admin/users", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert body["total"] >= 3  # seeded_users created admin+marketer+viewer

    def test_pagination_works(self, client, admin_headers, seeded_users):
        r = client.get("/api/admin/users?page=1&page_size=2", headers=admin_headers)
        body = r.json()
        assert len(body["items"]) == 2

    def test_viewer_cannot_list_users(self, client, viewer_headers):
        r = client.get("/api/admin/users", headers=viewer_headers)
        assert r.status_code == 403


class TestGetUser:
    def test_admin_can_get_user(self, client, admin_headers, seeded_users):
        users = client.get("/api/admin/users", headers=admin_headers).json()["items"]
        uid = users[0]["id"]
        r = client.get(f"/api/admin/users/{uid}", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["id"] == uid

    def test_nonexistent_user_returns_404(self, client, admin_headers, seeded_users):
        r = client.get("/api/admin/users/9999", headers=admin_headers)
        assert r.status_code == 404


class TestUpdateUser:
    def test_admin_can_change_role(self, client, admin_headers, seeded_users):
        # Create a user to update (avoid modifying self)
        create_r = client.post(
            "/api/admin/users",
            json={"email": "target@test.com", "password": "Target123!", "role": "viewer"},
            headers=admin_headers,
        )
        uid = create_r.json()["id"]
        r = client.put(
            f"/api/admin/users/{uid}",
            json={"role": "marketer"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["role"] == "marketer"

    def test_nonexistent_user_returns_404(self, client, admin_headers, seeded_users):
        r = client.put("/api/admin/users/9999", json={"role": "viewer"}, headers=admin_headers)
        assert r.status_code == 404

    def test_viewer_cannot_update_users(self, client, viewer_headers, admin_headers, seeded_users):
        users = client.get("/api/admin/users", headers=admin_headers).json()["items"]
        uid = users[0]["id"]
        r = client.put(f"/api/admin/users/{uid}", json={"role": "viewer"}, headers=viewer_headers)
        assert r.status_code == 403


class TestDeactivateUser:
    def test_admin_can_deactivate_user(self, client, admin_headers, seeded_users):
        create_r = client.post(
            "/api/admin/users",
            json={"email": "todelete@test.com", "password": "Delete123!", "role": "viewer"},
            headers=admin_headers,
        )
        uid = create_r.json()["id"]
        r = client.delete(f"/api/admin/users/{uid}", headers=admin_headers)
        assert r.status_code == 204

    def test_nonexistent_user_returns_404(self, client, admin_headers, seeded_users):
        r = client.delete("/api/admin/users/9999", headers=admin_headers)
        assert r.status_code == 404

    def test_viewer_cannot_deactivate_users(self, client, viewer_headers, admin_headers, seeded_users):
        create_r = client.post(
            "/api/admin/users",
            json={"email": "todelete@test.com", "password": "Delete123!", "role": "viewer"},
            headers=admin_headers,
        )
        uid = create_r.json()["id"]
        r = client.delete(f"/api/admin/users/{uid}", headers=viewer_headers)
        assert r.status_code == 403
