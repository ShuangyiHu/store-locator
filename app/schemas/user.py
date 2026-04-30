from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_VALID_ROLES = ("admin", "marketer", "viewer")
_VALID_STATUSES = ("active", "inactive")


class UserResponse(BaseModel):
    """User payload returned from auth and admin endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None = None
    role: str
    status: str
    must_change_password: bool
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def _role_to_name(cls, v):
        return v.name if hasattr(v, "name") else v

    @field_validator("status", mode="before")
    @classmethod
    def _enum_to_value(cls, v):
        return v.value if hasattr(v, "value") else v


class UserCreate(BaseModel):
    """Admin-only: provision a new user."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = Field(None, max_length=255)
    role: str

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"role must be one of {list(_VALID_ROLES)}")
        return v


class UserUpdate(BaseModel):
    """Admin-only: PUT may update role and/or status. Email/password are
    intentionally not updatable here — separate endpoints would handle those.
    """

    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    status: str | None = None

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in _VALID_ROLES:
            raise ValueError(f"role must be one of {list(_VALID_ROLES)}")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {list(_VALID_STATUSES)}")
        return v
