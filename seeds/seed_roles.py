"""Idempotent seed: services + permissions + roles + role-permission mappings.

Run: python -m seeds.seed_roles
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python seeds/seed_roles.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.role import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    Role,
)
from app.models.store import ALLOWED_SERVICES, Service


def _upsert_named(db: Session, model, names: tuple[str, ...]) -> dict[str, object]:
    existing = {row.name: row for row in db.execute(select(model)).scalars()}
    for name in names:
        if name not in existing:
            row = model(name=name)
            db.add(row)
            existing[name] = row
    db.flush()
    return existing


def seed(db: Session) -> None:
    services = _upsert_named(db, Service, ALLOWED_SERVICES)
    permissions = _upsert_named(db, Permission, ALL_PERMISSIONS)

    role_count = 0
    for role_name, perm_names in ROLE_PERMISSIONS.items():
        role = db.execute(
            select(Role).where(Role.name == role_name)
        ).scalar_one_or_none()
        if role is None:
            role = Role(name=role_name, description=f"{role_name.title()} role")
            db.add(role)
            db.flush()
        # Re-sync permissions every run so seed stays authoritative
        role.permissions = [permissions[p] for p in perm_names]
        role_count += 1

    db.commit()
    print(
        f"Seeded: {len(services)} services, "
        f"{len(permissions)} permissions, {role_count} roles"
    )


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
