from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)


class TestPasswordHashing:
    def test_round_trip(self):
        h = hash_password("hunter2!")
        assert verify_password("hunter2!", h) is True

    def test_wrong_password_fails(self):
        h = hash_password("hunter2!")
        assert verify_password("wrong", h) is False

    def test_truncates_at_72_bytes_consistently(self):
        # bcrypt limit. Two passwords identical in first 72 bytes should compare equal.
        long_a = "a" * 72 + "DIFFERENT"
        long_b = "a" * 72 + "ALSO_DIFFERENT"
        h = hash_password(long_a)
        assert verify_password(long_b, h) is True  # both truncated to 72*'a'

    def test_corrupted_hash_fails_safe(self):
        assert verify_password("anything", "not-a-bcrypt-hash") is False


class TestAccessToken:
    def test_payload_round_trip(self):
        token = create_access_token(user_id=42, email="x@y.com", role="admin")
        payload = decode_access_token(token)
        assert payload["sub"] == "42"
        assert payload["email"] == "x@y.com"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_expired_token_raises(self):
        # Forge a token with exp in the past
        settings = get_settings()
        past = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
        token = jwt.encode(
            {"sub": "1", "email": "x@y.com", "role": "admin", "exp": past, "type": "access"},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_wrong_signature_raises(self):
        settings = get_settings()
        token = jwt.encode(
            {"sub": "1", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()), "type": "access"},
            "WRONG-SECRET",
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(jwt.InvalidSignatureError):
            decode_access_token(token)

    def test_refresh_token_disguised_as_access_rejected(self):
        # A token with type != "access" must be rejected even if signature is valid.
        settings = get_settings()
        token = jwt.encode(
            {"sub": "1", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()), "type": "refresh"},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)


class TestRefreshTokenHelpers:
    def test_generate_returns_random_unique_tokens(self):
        tokens = {generate_refresh_token() for _ in range(20)}
        assert len(tokens) == 20  # all unique

    def test_hash_token_is_deterministic(self):
        assert hash_token("abc") == hash_token("abc")
        assert hash_token("abc") != hash_token("abd")

    def test_hash_token_returns_64_hex_chars(self):
        h = hash_token("anything")
        assert len(h) == 64
        int(h, 16)  # parses as hex
