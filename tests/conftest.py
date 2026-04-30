"""Test fixtures.

Strategy:
  - In-memory SQLite per test (fresh schema via Base.metadata.create_all)
  - Override `get_db` so requests share the test session
  - Stub geocoding everywhere it's imported (autouse) so tests never hit Nominatim
  - RATE_LIMIT_ENABLED=false so the rate limiter dependency short-circuits
  - Password hashes for the three seed users are pre-computed once per session
    to avoid eating multiple seconds of bcrypt work per test
"""

# ---- env MUST be set before any `from app...` import ----
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-please-only-for-tests-32+")
os.environ.setdefault("NOMINATIM_USER_AGENT", "test-agent/1.0 (tests)")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

# Make sure the lru_cached settings reflect the env vars set above.
get_settings.cache_clear()

from app import models  # noqa: F401  -- registers all ORM models
from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models.role import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    Role,
)
from app.models.store import ALLOWED_SERVICES, Service
from app.models.user import User, UserStatus

# Pre-compute bcrypt hashes once per test session — bcrypt is intentionally
# slow, paying that cost per-test would dominate runtime.
_TEST_PASSWORDS = {
    "admin@test.com": "AdminTest123!",
    "marketer@test.com": "MarketerTest123!",
    "viewer@test.com": "ViewerTest123!",
}
_TEST_HASHES = {email: hash_password(pw) for email, pw in _TEST_PASSWORDS.items()}


# ---- engine + session ----


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    TestSession = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


# ---- TestClient with get_db override ----


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass  # session lifecycle owned by db_session fixture

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---- Geocode stub (autouse — tests never hit Nominatim) ----


@pytest.fixture(autouse=True)
def mock_geocode(monkeypatch):
    fake_results = {
        "32801": (28.5432, -81.3767),
        "boston, ma": (42.3601, -71.0589),
        "orlando, fl": (28.5421, -81.3790),
        "1 beacon st, boston, ma 02108": (42.3601, -71.0589),
    }

    def fake(query: str | None):
        if not query or not query.strip():
            return None
        normalized = " ".join(query.lower().strip().split())
        if normalized in fake_results:
            return fake_results[normalized]
        if "1600 pennsylvania" in normalized:
            return (38.8976, -77.0366)
        if "bogus" in normalized or "asdfgh" in normalized:
            return None
        # Reasonable default — Boston-area
        return (42.0, -71.0)

    monkeypatch.setattr("app.services.geo_service.geocode", fake)
    monkeypatch.setattr("app.services.store_service.geocode", fake, raising=False)
    monkeypatch.setattr("app.services.csv_service.geocode", fake)


# ---- Seed fixtures ----


@pytest.fixture
def seeded_roles(db_session: Session) -> Session:
    """Create services + permissions + roles + role-permission mapping."""
    services = [Service(name=n) for n in ALLOWED_SERVICES]
    perms = [Permission(name=n) for n in ALL_PERMISSIONS]
    db_session.add_all(services + perms)
    db_session.flush()

    perm_lookup = {p.name: p for p in perms}
    for role_name, perm_names in ROLE_PERMISSIONS.items():
        role = Role(name=role_name, description=f"{role_name.title()} role")
        role.permissions = [perm_lookup[p] for p in perm_names]
        db_session.add(role)
    db_session.commit()
    return db_session


@pytest.fixture
def seeded_users(seeded_roles: Session) -> Session:
    """admin/marketer/viewer with pre-hashed passwords."""
    role_by_name = {r.name: r for r in seeded_roles.query(Role).all()}
    seeded_roles.add_all([
        User(
            email=email,
            password_hash=_TEST_HASHES[email],
            full_name=f"{role_name.title()} User",
            role_id=role_by_name[role_name].id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        for email, role_name in [
            ("admin@test.com", "admin"),
            ("marketer@test.com", "marketer"),
            ("viewer@test.com", "viewer"),
        ]
    ])
    seeded_roles.commit()
    return seeded_roles


# ---- Auth headers per role ----


def _login(client: TestClient, email: str) -> str:
    r = client.post(
        "/api/auth/login",
        json={"email": email, "password": _TEST_PASSWORDS[email]},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def admin_headers(client: TestClient, seeded_users: Session) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client, 'admin@test.com')}"}


@pytest.fixture
def marketer_headers(client: TestClient, seeded_users: Session) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client, 'marketer@test.com')}"}


@pytest.fixture
def viewer_headers(client: TestClient, seeded_users: Session) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client, 'viewer@test.com')}"}
