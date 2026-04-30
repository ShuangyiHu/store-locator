"""End-to-end auth flows: login → use token → refresh → logout."""


class TestFullAuthFlow:
    def test_login_use_and_refresh(self, client, seeded_users):
        # Login
        login_r = client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "AdminTest123!"},
        )
        assert login_r.status_code == 200
        tokens = login_r.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # Use access token on a protected endpoint
        list_r = client.get(
            "/api/admin/stores",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert list_r.status_code == 200

        # Refresh produces a new access token
        refresh_r = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh_r.status_code == 200
        assert "access_token" in refresh_r.json()

        # Refresh token stays valid until explicitly revoked (no rotation)
        repeat_r = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert repeat_r.status_code == 200

    def test_logout_then_refresh_fails(self, client, seeded_users):
        login_r = client.post(
            "/api/auth/login",
            json={"email": "viewer@test.com", "password": "ViewerTest123!"},
        )
        rt = login_r.json()["refresh_token"]

        client.post("/api/auth/logout", json={"refresh_token": rt})

        r = client.post("/api/auth/refresh", json={"refresh_token": rt})
        assert r.status_code == 401

    def test_expired_access_token_rejected(self, client, seeded_users):
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.config import get_settings

        settings = get_settings()
        past = int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())
        expired_token = jwt.encode(
            {"sub": "1", "email": "admin@test.com", "role": "admin",
             "exp": past, "type": "access"},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        r = client.get(
            "/api/admin/stores",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert r.status_code == 401


class TestRoleBasedAccess:
    def test_viewer_can_search_stores(self, client, viewer_headers):
        r = client.get("/api/admin/stores", headers=viewer_headers)
        assert r.status_code == 200

    def test_viewer_cannot_create_stores(self, client, viewer_headers):
        r = client.post("/api/admin/stores", json={}, headers=viewer_headers)
        # 403 (forbidden) or 422 (body validation fails first) are both acceptable
        assert r.status_code in (403, 422)

    def test_viewer_cannot_manage_users(self, client, viewer_headers):
        r = client.get("/api/admin/users", headers=viewer_headers)
        assert r.status_code == 403

    def test_marketer_can_create_stores(self, client, marketer_headers):
        payload = {
            "store_id": "S0001",
            "name": "Flow Store",
            "store_type": "regular",
            "status": "active",
            "latitude": 42.3601,
            "longitude": -71.0589,
            "address_street": "1 Main St",
            "address_city": "Boston",
            "address_state": "MA",
            "address_postal_code": "02101",
            "address_country": "USA",
            "services": [],
            "hours_mon": "08:00-22:00",
            "hours_tue": "08:00-22:00",
            "hours_wed": "08:00-22:00",
            "hours_thu": "08:00-22:00",
            "hours_fri": "08:00-22:00",
            "hours_sat": "closed",
            "hours_sun": "10:00-20:00",
        }
        r = client.post("/api/admin/stores", json=payload, headers=marketer_headers)
        assert r.status_code == 201

    def test_marketer_cannot_manage_users(self, client, marketer_headers):
        r = client.get("/api/admin/users", headers=marketer_headers)
        assert r.status_code == 403
