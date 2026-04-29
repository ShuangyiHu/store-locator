"""Seed stores from CSV. Idempotent (skips existing store_ids).

Use stores_50.csv for dev, stores_1000.csv for the full dataset.

Run: python -m seeds.seed_stores                    # uses stores_50.csv
     python -m seeds.seed_stores data/stores_1000.csv

This is a thin "load known-good CSV" loader; full validation/upsert lives in
the CSV import service (Phase 5).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.store import Service, Store, StoreStatus, StoreType


_DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "stores_50.csv"

_HOUR_FIELDS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _row_to_store(row: dict, services_by_name: dict[str, Service]) -> Store:
    store = Store(
        store_id=row["store_id"],
        name=row["name"],
        store_type=StoreType(row["store_type"]),
        status=StoreStatus(row["status"]),
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        address_street=row["address_street"],
        address_city=row["address_city"],
        address_state=row["address_state"],
        address_postal_code=row["address_postal_code"],
        address_country=row["address_country"],
        phone=row["phone"] or None,
        **{f"hours_{day}": row[f"hours_{day}"] for day in _HOUR_FIELDS},
    )
    raw_services = (row.get("services") or "").strip()
    if raw_services:
        for name in raw_services.split("|"):
            name = name.strip()
            if name and name in services_by_name:
                store.services.append(services_by_name[name])
    return store


def seed(db: Session, csv_path: Path) -> tuple[int, int]:
    services_by_name = {s.name: s for s in db.execute(select(Service)).scalars()}
    if not services_by_name:
        raise RuntimeError("services table is empty — run seed_roles.py first")

    created = 0
    skipped = 0
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing = db.get(Store, row["store_id"])
            if existing is not None:
                skipped += 1
                continue
            db.add(_row_to_store(row, services_by_name))
            created += 1

    db.commit()
    return created, skipped


if __name__ == "__main__":
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_CSV
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    print(f"Seeding stores from {csv_path}")
    with SessionLocal() as db:
        created, skipped = seed(db, csv_path)
    print(f"Done: created={created}, skipped={skipped}")
