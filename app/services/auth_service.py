"""Auth business logic: login, refresh, logout.

Service-layer functions raise typed exceptions; routers map them to HTTP
status codes. This keeps the service free of FastAPI/HTTP concerns.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import security
from app.models.token import RefreshToken
from app.models.user import User, UserStatus


class AuthError(Exception):
    """Base for auth failures (mapped to 401 by the router)."""


class InvalidCredentialsError(AuthError):
    pass


class InactiveUserError(AuthError):
    pass


class InvalidRefreshTokenError(AuthError):
    pass


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.execute(
        select(User).where(User.email == email.lower())
    ).scalar_one_or_none()
    if user is None or not security.verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    if user.status != UserStatus.ACTIVE:
        raise InactiveUserError()
    return user


def login(db: Session, email: str, password: str) -> tuple[User, str, str]:
    """Returns (user, access_token, raw_refresh_token)."""
    settings = get_settings()
    user = authenticate_user(db, email, password)

    access_token = security.create_access_token(user.id, user.email, user.role.name)
    raw_refresh = security.generate_refresh_token()

    db.add(
        RefreshToken(
            token_hash=security.hash_token(raw_refresh),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
            revoked=False,
        )
    )
    db.commit()

    return user, access_token, raw_refresh


def refresh_access_token(db: Session, raw_refresh: str) -> tuple[User, str]:
    token_hash = security.hash_token(raw_refresh)
    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if row is None or row.revoked:
        raise InvalidRefreshTokenError()

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise InvalidRefreshTokenError()

    user = db.get(User, row.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise InvalidRefreshTokenError()

    access_token = security.create_access_token(user.id, user.email, user.role.name)
    return user, access_token


def logout(db: Session, raw_refresh: str) -> None:
    """Revoke the refresh token. Idempotent — silent on unknown tokens."""
    token_hash = security.hash_token(raw_refresh)
    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if row is not None and not row.revoked:
        row.revoked = True
        db.commit()
