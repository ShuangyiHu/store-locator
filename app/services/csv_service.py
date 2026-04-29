"""CSV bulk-import service.

Three-phase pipeline (per requirements §2.3):
  1. Parse + per-row syntactic validation. No DB or network calls.
  2. Enrichment: geocode rows missing lat/lon. Adds errors on geocode miss.
  3. Upsert in a single transaction. ALL-or-nothing — any error rolls back.

Errors from phases 1 and 2 are collected and returned together. The
transaction in phase 3 only runs if phases 1 + 2 produced zero errors.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.store import (
    ALLOWED_SERVICES,
    Service,
    Store,
    StoreStatus,
    StoreType,
)
from app.schemas.common import CSVImportError, CSVImportReport
from app.services.geo_service import geocode
from app.utils.hours import parse_hours

REQUIRED_COLUMNS: tuple[str, ...] = (
    "store_id", "name", "store_type", "status",
    "latitude", "longitude",
    "address_street", "address_city", "address_state",
    "address_postal_code", "address_country",
    "phone", "services",
    "hours_mon", "hours_tue", "hours_wed", "hours_thu",
    "hours_fri", "hours_sat", "hours_sun",
)

_HOUR_FIELDS = ("hours_mon", "hours_tue", "hours_wed", "hours_thu",
                "hours_fri", "hours_sat", "hours_sun")
_PHONE_RE = re.compile(r"^\d{3}-\d{3}-\d{4}$")
_POSTAL_RE = re.compile(r"^\d{5}$")
_STORE_ID_RE = re.compile(r"^S\d{4,}$")
_STATE_RE = re.compile(r"^[A-Z]{2}$")


class CSVStructureError(Exception):
    """CSV is missing required headers or has unexpected ones — not a row error."""


# --- Phase 1: parse + validate ---


def _validate_row(raw: dict[str, str], row_num: int) -> tuple[dict[str, Any] | None, list[CSVImportError]]:
    """Return (normalized_row | None, errors). normalized_row has parsed types."""
    errors: list[CSVImportError] = []

    def err(field: str, msg: str) -> None:
        errors.append(CSVImportError(row=row_num, field=field, message=msg))

    sid = (raw.get("store_id") or "").strip()
    if not sid:
        err("store_id", "required")
    elif not _STORE_ID_RE.match(sid):
        err("store_id", "must match S followed by 4+ digits")

    name = (raw.get("name") or "").strip()
    if not name:
        err("name", "required")

    store_type = (raw.get("store_type") or "").strip()
    valid_types = {t.value for t in StoreType}
    if store_type not in valid_types:
        err("store_type", f"must be one of {sorted(valid_types)}")

    status_str = (raw.get("status") or "").strip()
    valid_statuses = {s.value for s in StoreStatus}
    if status_str not in valid_statuses:
        err("status", f"must be one of {sorted(valid_statuses)}")

    lat: float | None = None
    lon: float | None = None
    lat_str = (raw.get("latitude") or "").strip()
    lon_str = (raw.get("longitude") or "").strip()
    if lat_str and lon_str:
        try:
            lat = float(lat_str)
            if not -90 <= lat <= 90:
                err("latitude", "must be between -90 and 90")
                lat = None
        except ValueError:
            err("latitude", "must be a number")
        try:
            lon = float(lon_str)
            if not -180 <= lon <= 180:
                err("longitude", "must be between -180 and 180")
                lon = None
        except ValueError:
            err("longitude", "must be a number")
    elif lat_str or lon_str:
        err(
            "latitude" if lon_str else "longitude",
            "latitude and longitude must be provided together",
        )
    # else: both empty → defer to enrichment phase

    street = (raw.get("address_street") or "").strip()
    if not street:
        err("address_street", "required")
    city = (raw.get("address_city") or "").strip()
    if not city:
        err("address_city", "required")

    state = (raw.get("address_state") or "").strip()
    if not _STATE_RE.match(state):
        err("address_state", "must be a 2-letter uppercase code")

    postal = (raw.get("address_postal_code") or "").strip()
    if not _POSTAL_RE.match(postal):
        err("address_postal_code", "must be 5 digits")

    country = (raw.get("address_country") or "").strip() or "USA"

    phone = (raw.get("phone") or "").strip()
    if phone and not _PHONE_RE.match(phone):
        err("phone", "must match XXX-XXX-XXXX")

    services_raw = (raw.get("services") or "").strip()
    services = (
        [s.strip() for s in services_raw.split("|") if s.strip()]
        if services_raw
        else []
    )
    invalid_services = [s for s in services if s not in ALLOWED_SERVICES]
    if invalid_services:
        err("services", f"unknown services: {invalid_services}")

    hours: dict[str, str] = {}
    for col in _HOUR_FIELDS:
        v = (raw.get(col) or "").strip()
        try:
            parse_hours(v)
        except ValueError as exc:
            err(col, str(exc))
        hours[col] = v

    if errors:
        return None, errors

    return {
        "store_id": sid,
        "name": name,
        "store_type": store_type,
        "status": status_str,
        "latitude": lat,
        "longitude": lon,
        "address_street": street,
        "address_city": city,
        "address_state": state,
        "address_postal_code": postal,
        "address_country": country,
        "phone": phone or None,
        "services": services,
        **hours,
        "_row_num": row_num,
    }, []


def _parse_csv(content: bytes) -> tuple[list[dict[str, Any]], list[CSVImportError]]:
    text = content.decode("utf-8-sig")  # tolerate UTF-8 BOM
    reader = csv.DictReader(io.StringIO(text))

    actual = list(reader.fieldnames or [])
    expected = list(REQUIRED_COLUMNS)
    if actual != expected:
        missing = [c for c in expected if c not in actual]
        extra = [c for c in actual if c not in expected]
        raise CSVStructureError(
            f"CSV header mismatch. Missing: {missing}, Unexpected: {extra}"
        )

    rows: list[dict[str, Any]] = []
    all_errors: list[CSVImportError] = []
    for idx, raw in enumerate(reader, start=1):  # row 1 = first data row (header excluded)
        normalized, errors = _validate_row(raw, idx)
        if errors:
            all_errors.extend(errors)
        elif normalized is not None:
            rows.append(normalized)
    return rows, all_errors


# --- Phase 2: enrich ---


def _format_address(row: dict[str, Any]) -> str:
    return (
        f"{row['address_street']}, {row['address_city']}, "
        f"{row['address_state']} {row['address_postal_code']}"
    )


def _enrich_geocode(rows: list[dict[str, Any]]) -> list[CSVImportError]:
    errors: list[CSVImportError] = []
    for row in rows:
        if row["latitude"] is not None and row["longitude"] is not None:
            continue
        result = geocode(_format_address(row))
        if result is None:
            errors.append(
                CSVImportError(
                    row=row["_row_num"],
                    field="latitude",
                    message=f"could not geocode address: {_format_address(row)}",
                )
            )
            continue
        row["latitude"], row["longitude"] = result
    return errors


# --- Phase 3: upsert ---


def _apply_row(
    row: dict[str, Any],
    services_by_name: dict[str, Service],
    existing: Store | None,
) -> tuple[Store, bool]:
    """Apply a row to a Store (new or existing). Returns (store, was_created)."""
    if existing is None:
        store = Store(store_id=row["store_id"])
        created = True
    else:
        store = existing
        created = False

    store.name = row["name"]
    store.store_type = StoreType(row["store_type"])
    store.status = StoreStatus(row["status"])
    store.latitude = row["latitude"]
    store.longitude = row["longitude"]
    store.address_street = row["address_street"]
    store.address_city = row["address_city"]
    store.address_state = row["address_state"]
    store.address_postal_code = row["address_postal_code"]
    store.address_country = row["address_country"]
    store.phone = row["phone"]
    for col in _HOUR_FIELDS:
        setattr(store, col, row[col])

    store.services = [
        services_by_name[name]
        for name in row["services"]
        if name in services_by_name
    ]
    return store, created


def import_stores_from_csv(db: Session, content: bytes) -> CSVImportReport:
    """Validate + upsert. All-or-nothing transaction.

    Raises CSVStructureError if headers don't match (caller maps to 400).
    """
    rows, errors = _parse_csv(content)
    total = len(rows) + len({e.row for e in errors})

    if errors:
        return CSVImportReport(
            total=total,
            created=0,
            updated=0,
            failed=len({e.row for e in errors}),
            errors=errors,
            success=False,
        )

    enrich_errors = _enrich_geocode(rows)
    if enrich_errors:
        return CSVImportReport(
            total=total,
            created=0,
            updated=0,
            failed=len({e.row for e in enrich_errors}),
            errors=enrich_errors,
            success=False,
        )

    services_by_name = {s.name: s for s in db.execute(select(Service)).scalars()}

    try:
        created = 0
        updated = 0
        for row in rows:
            existing = db.get(Store, row["store_id"])
            _store, was_created = _apply_row(row, services_by_name, existing)
            if was_created:
                db.add(_store)
                created += 1
            else:
                updated += 1
        db.commit()
    except Exception:
        db.rollback()
        raise

    return CSVImportReport(
        total=created + updated,
        created=created,
        updated=updated,
        failed=0,
        errors=[],
        success=True,
    )
