"""Store search business logic.

Pipeline (per requirements §1.4):
  1. Resolve search location → (lat, lon) via geocoding if needed
  2. Compute degree-based bounding box
  3. SQL pre-filter (status, lat/lon BETWEEN, store_type, services AND)
  4. Compute exact haversine distance for candidates
  5. Filter by exact radius, optionally by `open_now`
  6. Sort by distance ASC, apply `limit`
"""

from __future__ import annotations

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.store import (
    Service,
    Store,
    StoreStatus,
    StoreType,
    store_services,
)
from app.schemas.store import (
    SearchMetadata,
    SearchRequest,
    SearchResponse,
    StoreAddress,
    StoreCreate,
    StoreHours,
    StoreSearchResult,
    StoreUpdate,
)
from app.services.geo_service import geocode
from app.utils.distance import bounding_box, haversine_miles
from app.utils.hours import is_open_now, store_hours_dict


class LocationNotFoundError(Exception):
    """Address or postal code could not be geocoded."""


class DuplicateStoreError(Exception):
    """A store with this store_id already exists."""


def _resolve_location(req: SearchRequest) -> tuple[float, float, str]:
    """Return (lat, lon, resolved_from). Raises LocationNotFoundError on geocode miss."""
    if req.latitude is not None and req.longitude is not None:
        return (req.latitude, req.longitude, "coordinates")

    if req.postal_code:
        result = geocode(req.postal_code)
        if result is None:
            raise LocationNotFoundError(
                f"Could not resolve postal code: {req.postal_code}"
            )
        return (result[0], result[1], "postal_code")

    # address (model_validator guarantees at least one is set)
    assert req.address is not None
    result = geocode(req.address)
    if result is None:
        raise LocationNotFoundError(f"Could not resolve address: {req.address}")
    return (result[0], result[1], "address")


def _build_query(
    req: SearchRequest,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
):
    """Compose the SQL pre-filter. Returns a SQLAlchemy select() statement."""
    stmt = select(Store).where(
        Store.status.in_([StoreStatus.ACTIVE, StoreStatus.TEMPORARILY_CLOSED]),
        Store.latitude.between(min_lat, max_lat),
        Store.longitude.between(min_lon, max_lon),
    )

    if req.store_types:
        # OR logic — match any of the requested types
        stmt = stmt.where(
            Store.store_type.in_([StoreType(t) for t in req.store_types])
        )

    if req.services:
        # AND logic — store must have ALL requested services.
        # Single subquery using GROUP BY + HAVING COUNT for efficiency.
        services_subq = (
            select(store_services.c.store_id)
            .join(Service, Service.id == store_services.c.service_id)
            .where(Service.name.in_(req.services))
            .group_by(store_services.c.store_id)
            .having(func.count(distinct(Service.id)) == len(req.services))
        )
        stmt = stmt.where(Store.store_id.in_(services_subq))

    return stmt


def _to_result(store: Store, distance: float, is_open: bool) -> StoreSearchResult:
    return StoreSearchResult(
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
        hours=StoreHours(**store_hours_dict(store)),
        distance_miles=round(distance, 3),
        is_open_now=is_open,
    )


def search_stores(db: Session, req: SearchRequest) -> SearchResponse:
    lat, lon, resolved_from = _resolve_location(req)
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, req.radius_miles)

    stmt = _build_query(req, min_lat, max_lat, min_lon, max_lon)
    candidates = db.execute(stmt).scalars().all()

    scored: list[tuple[Store, float, bool]] = []
    for store in candidates:
        distance = haversine_miles(lat, lon, store.latitude, store.longitude)
        if distance > req.radius_miles:
            continue
        is_open = is_open_now(store_hours_dict(store))
        if req.open_now and not is_open:
            continue
        scored.append((store, distance, is_open))

    scored.sort(key=lambda triple: triple[1])
    scored = scored[: req.limit]

    return SearchResponse(
        metadata=SearchMetadata(
            search_latitude=lat,
            search_longitude=lon,
            resolved_from=resolved_from,
            radius_miles=req.radius_miles,
            filters_applied={
                "services": req.services,
                "store_types": req.store_types,
                "open_now": req.open_now,
            },
        ),
        count=len(scored),
        results=[_to_result(s, d, o) for s, d, o in scored],
    )


# --- Admin CRUD ---

_HOUR_FIELDS = ("hours_mon", "hours_tue", "hours_wed", "hours_thu",
                "hours_fri", "hours_sat", "hours_sun")


def _format_address(payload: StoreCreate) -> str:
    return (
        f"{payload.address_street}, {payload.address_city}, "
        f"{payload.address_state} {payload.address_postal_code}"
    )


def _services_lookup(db: Session) -> dict[str, Service]:
    return {s.name: s for s in db.execute(select(Service)).scalars()}


def create_store(db: Session, payload: StoreCreate) -> Store:
    if db.get(Store, payload.store_id) is not None:
        raise DuplicateStoreError(f"Store {payload.store_id} already exists")

    lat, lon = payload.latitude, payload.longitude
    if lat is None or lon is None:
        from app.services.geo_service import geocode  # local import: avoid cycle at module load
        result = geocode(_format_address(payload))
        if result is None:
            raise LocationNotFoundError(
                f"Could not geocode address for new store: {_format_address(payload)}"
            )
        lat, lon = result

    services_by_name = _services_lookup(db)

    store = Store(
        store_id=payload.store_id,
        name=payload.name,
        store_type=StoreType(payload.store_type),
        status=StoreStatus(payload.status),
        latitude=lat,
        longitude=lon,
        address_street=payload.address_street,
        address_city=payload.address_city,
        address_state=payload.address_state,
        address_postal_code=payload.address_postal_code,
        address_country=payload.address_country,
        phone=payload.phone,
        **{f: getattr(payload, f) for f in _HOUR_FIELDS},
    )
    store.services = [services_by_name[s] for s in payload.services if s in services_by_name]
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def get_store(db: Session, store_id: str) -> Store | None:
    return db.get(Store, store_id)


def list_stores(
    db: Session,
    page: int,
    page_size: int,
    status_filter: StoreStatus | None = None,
) -> tuple[list[Store], int]:
    base = select(Store)
    if status_filter is not None:
        base = base.where(Store.status == status_filter)

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()

    items = db.execute(
        base.order_by(Store.store_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    return list(items), int(total)


def partial_update_store(
    db: Session, store_id: str, payload: StoreUpdate
) -> Store | None:
    store = db.get(Store, store_id)
    if store is None:
        return None

    data = payload.model_dump(exclude_unset=True)

    for field, value in data.items():
        if field == "status":
            store.status = StoreStatus(value)
        elif field == "services":
            services_by_name = _services_lookup(db)
            store.services = [
                services_by_name[s] for s in value if s in services_by_name
            ]
        else:
            # name, phone, hours_*  — set directly
            setattr(store, field, value)

    db.commit()
    db.refresh(store)
    return store


def soft_delete_store(db: Session, store_id: str) -> bool:
    store = db.get(Store, store_id)
    if store is None:
        return False
    store.status = StoreStatus.INACTIVE
    db.commit()
    return True
