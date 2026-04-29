from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


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
