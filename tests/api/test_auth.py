class TestLogin:
    def test_login_success(self, client, seeded_users):
        r = client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "AdminTest123!"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["user"]["email"] == "admin@test.com"
        assert body["user"]["role"] == "admin"

    def test_login_wrong_password(self, client, seeded_users):
        r = client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "wrongpassword"},
        )
        assert r.status_code == 401

    def test_login_unknown_email(self, client, seeded_users):
        r = client.post(
            "/api/auth/login",
            json={"email": "nobody@test.com", "password": "SomePass123!"},
        )
        assert r.status_code == 401

    def test_login_invalid_email_format(self, client, seeded_users):
        r = client.post(
            "/api/auth/login",
            json={"email": "not-an-email", "password": "password"},
        )
        assert r.status_code == 422

    def test_login_all_roles_succeed(self, client, seeded_users):
        for email, pw, role in [
            ("admin@test.com", "AdminTest123!", "admin"),
            ("marketer@test.com", "MarketerTest123!", "marketer"),
            ("viewer@test.com", "ViewerTest123!", "viewer"),
        ]:
            r = client.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200
            assert r.json()["user"]["role"] == role


class TestRefresh:
    def test_refresh_returns_new_access_token(self, client, seeded_users):
        login = client.post(
            "/api/auth/login",
            json={"email": "viewer@test.com", "password": "ViewerTest123!"},
        ).json()
        r = client.post(
            "/api/auth/refresh",
            json={"refresh_token": login["refresh_token"]},
        )
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_refresh_with_invalid_token(self, client, seeded_users):
        r = client.post("/api/auth/refresh", json={"refresh_token": "not-a-real-token"})
        assert r.status_code == 401

    def test_refresh_token_usable_until_logout(self, client, seeded_users):
        login = client.post(
            "/api/auth/login",
            json={"email": "viewer@test.com", "password": "ViewerTest123!"},
        ).json()
        rt = login["refresh_token"]
        r1 = client.post("/api/auth/refresh", json={"refresh_token": rt})
        assert r1.status_code == 200
        # Token is still valid until explicitly revoked via logout
        r2 = client.post("/api/auth/refresh", json={"refresh_token": rt})
        assert r2.status_code == 200


class TestLogout:
    def test_logout_returns_204(self, client, seeded_users):
        login = client.post(
            "/api/auth/login",
            json={"email": "viewer@test.com", "password": "ViewerTest123!"},
        ).json()
        r = client.post("/api/auth/logout", json={"refresh_token": login["refresh_token"]})
        assert r.status_code == 204

    def test_logout_invalidates_refresh_token(self, client, seeded_users):
        login = client.post(
            "/api/auth/login",
            json={"email": "viewer@test.com", "password": "ViewerTest123!"},
        ).json()
        rt = login["refresh_token"]
        client.post("/api/auth/logout", json={"refresh_token": rt})
        r = client.post("/api/auth/refresh", json={"refresh_token": rt})
        assert r.status_code == 401
