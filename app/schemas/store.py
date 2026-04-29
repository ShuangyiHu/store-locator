from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.store import ALLOWED_SERVICES, StoreStatus, StoreType
from app.utils.hours import parse_hours

_PHONE_RE = re.compile(r"^\d{3}-\d{3}-\d{4}$")
_POSTAL_RE = re.compile(r"^\d{5}$")
_STORE_ID_RE = re.compile(r"^S\d{4,}$")
_STATE_RE = re.compile(r"^[A-Z]{2}$")
_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _validate_hours_value(v: str) -> str:
    parse_hours(v)  # raises ValueError on bad format
    return v


def _validate_services_list(v: list[str]) -> list[str]:
    unique = list(dict.fromkeys(v))
    invalid = [s for s in unique if s not in ALLOWED_SERVICES]
    if invalid:
        raise ValueError(f"Unknown services: {invalid}")
    return unique


class SearchRequest(BaseModel):
    """One-of: address | postal_code | (latitude + longitude). Plus filters."""

    model_config = ConfigDict(extra="forbid")

    address: str | None = None
    postal_code: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

    radius_miles: float = Field(10.0, gt=0, le=100)
    services: list[str] = Field(default_factory=list, description="AND filter")
    store_types: list[str] = Field(default_factory=list, description="OR filter")
    open_now: bool = False
    limit: int = Field(20, ge=1, le=100)

    @field_validator("services", mode="after")
    @classmethod
    def _validate_services(cls, v: list[str]) -> list[str]:
        return _validate_services_list(v)

    @field_validator("store_types", mode="after")
    @classmethod
    def _validate_store_types(cls, v: list[str]) -> list[str]:
        unique = list(dict.fromkeys(v))
        valid = {t.value for t in StoreType}
        invalid = [t for t in unique if t not in valid]
        if invalid:
            raise ValueError(f"Unknown store_types: {invalid}")
        return unique

    @model_validator(mode="after")
    def _exactly_one_location(self):
        has_coords = self.latitude is not None and self.longitude is not None
        has_partial_coords = (self.latitude is None) != (self.longitude is None)
        has_address = bool(self.address and self.address.strip())
        has_postal = bool(self.postal_code and self.postal_code.strip())

        if has_partial_coords:
            raise ValueError("latitude and longitude must be provided together")

        provided = sum([has_coords, has_address, has_postal])
        if provided == 0:
            raise ValueError(
                "Provide one of: address, postal_code, or (latitude + longitude)"
            )
        if provided > 1:
            raise ValueError(
                "Provide only one of: address, postal_code, or (latitude + longitude)"
            )
        return self


class StoreAddress(BaseModel):
    street: str
    city: str
    state: str
    postal_code: str
    country: str


class StoreHours(BaseModel):
    mon: str
    tue: str
    wed: str
    thu: str
    fri: str
    sat: str
    sun: str


class StoreSearchResult(BaseModel):
    store_id: str
    name: str
    store_type: str
    status: str
    latitude: float
    longitude: float
    address: StoreAddress
    phone: str | None
    services: list[str]
    hours: StoreHours
    distance_miles: float
    is_open_now: bool


class SearchMetadata(BaseModel):
    search_latitude: float
    search_longitude: float
    resolved_from: Literal["coordinates", "postal_code", "address"]
    radius_miles: float
    filters_applied: dict


class SearchResponse(BaseModel):
    metadata: SearchMetadata
    count: int
    results: list[StoreSearchResult]


# --- Admin CRUD ---


class StoreCreate(BaseModel):
    """Full payload for POST /api/admin/stores. Coords optional (auto-geocode)."""

    model_config = ConfigDict(extra="forbid")

    store_id: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=1, max_length=255)
    store_type: str
    status: str = StoreStatus.ACTIVE.value
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    address_street: str = Field(min_length=1, max_length=255)
    address_city: str = Field(min_length=1, max_length=100)
    address_state: str = Field(min_length=2, max_length=2)
    address_postal_code: str
    address_country: str = Field(default="USA", max_length=3)
    phone: str | None = None
    services: list[str] = Field(default_factory=list)
    hours_mon: str
    hours_tue: str
    hours_wed: str
    hours_thu: str
    hours_fri: str
    hours_sat: str
    hours_sun: str

    @field_validator("store_id")
    @classmethod
    def _validate_store_id(cls, v: str) -> str:
        if not _STORE_ID_RE.match(v):
            raise ValueError("store_id must match S followed by 4+ digits (e.g. S0001)")
        return v

    @field_validator("store_type")
    @classmethod
    def _validate_store_type(cls, v: str) -> str:
        valid = {t.value for t in StoreType}
        if v not in valid:
            raise ValueError(f"store_type must be one of {sorted(valid)}")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        valid = {s.value for s in StoreStatus}
        if v not in valid:
            raise ValueError(f"status must be one of {sorted(valid)}")
        return v

    @field_validator("address_state")
    @classmethod
    def _validate_state(cls, v: str) -> str:
        if not _STATE_RE.match(v):
            raise ValueError("address_state must be a 2-letter uppercase code")
        return v

    @field_validator("address_postal_code")
    @classmethod
    def _validate_postal(cls, v: str) -> str:
        if not _POSTAL_RE.match(v):
            raise ValueError("address_postal_code must be 5 digits")
        return v

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _PHONE_RE.match(v):
            raise ValueError("phone must match XXX-XXX-XXXX")
        return v

    @field_validator("services")
    @classmethod
    def _validate_services(cls, v: list[str]) -> list[str]:
        return _validate_services_list(v)

    @field_validator(
        "hours_mon", "hours_tue", "hours_wed", "hours_thu",
        "hours_fri", "hours_sat", "hours_sun",
    )
    @classmethod
    def _validate_hours(cls, v: str) -> str:
        return _validate_hours_value(v)

    @model_validator(mode="after")
    def _coords_paired(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class StoreUpdate(BaseModel):
    """PATCH payload — only mutable fields. extra='forbid' rejects attempts to PATCH
    immutable fields (store_id, latitude/longitude, address_*) with 422."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    phone: str | None = None
    services: list[str] | None = None
    status: str | None = None
    hours_mon: str | None = None
    hours_tue: str | None = None
    hours_wed: str | None = None
    hours_thu: str | None = None
    hours_fri: str | None = None
    hours_sat: str | None = None
    hours_sun: str | None = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid = {s.value for s in StoreStatus}
        if v not in valid:
            raise ValueError(f"status must be one of {sorted(valid)}")
        return v

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _PHONE_RE.match(v):
            raise ValueError("phone must match XXX-XXX-XXXX")
        return v

    @field_validator("services")
    @classmethod
    def _validate_services(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return _validate_services_list(v)

    @field_validator(
        "hours_mon", "hours_tue", "hours_wed", "hours_thu",
        "hours_fri", "hours_sat", "hours_sun",
    )
    @classmethod
    def _validate_hours(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_hours_value(v)


class StoreResponse(BaseModel):
    """Full store representation for admin endpoints."""

    store_id: str
    name: str
    store_type: str
    status: str
    latitude: float
    longitude: float
    address: StoreAddress
    phone: str | None
    services: list[str]
    hours: StoreHours
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_store(cls, store) -> "StoreResponse":
        return cls(
            store_id=store.store_id,
            name=store.name,
            store_type=store.store_type.value,
            status=store.status.value,
            latitude=store.latitude,
            longitude=store.longitude,
            address=StoreAddress(
                street=store.address_street,
                city=store.address_city,
                state=store.address_state,
                postal_code=store.address_postal_code,
                country=store.address_country,
            ),
            phone=store.phone,
            services=sorted(s.name for s in store.services),
            hours=StoreHours(
                **{day: getattr(store, f"hours_{day}") for day in _DAY_KEYS}
            ),
            created_at=store.created_at,
            updated_at=store.updated_at,
        )
