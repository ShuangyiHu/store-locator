"""Idempotent seed: 3 test users (admin / marketer / viewer).

Run: python -m seeds.seed_users  (requires seed_roles.py first)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database import SessionLocal
from app.models.role import Role
from app.models.user import User, UserStatus

SEED_USERS: list[tuple[str, str, str, str]] = [
    ("admin@test.com", "AdminTest123!", "Admin User", "admin"),
    ("marketer@test.com", "MarketerTest123!", "Marketer User", "marketer"),
    ("viewer@test.com", "ViewerTest123!", "Viewer User", "viewer"),
]


def seed(db: Session) -> None:
    roles_by_name = {r.name: r for r in db.execute(select(Role)).scalars()}

    created = 0
    skipped = 0
    for email, password, full_name, role_name in SEED_USERS:
        existing = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  SKIP  {email} (already exists)")
            skipped += 1
            continue
        role = roles_by_name.get(role_name)
        if role is None:
            print(f"  ERROR role '{role_name}' not found — run seed_roles.py first")
            continue
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role_id=role.id,
                status=UserStatus.ACTIVE,
                must_change_password=False,  # test users — bypass change-on-login
            )
        )
        print(f"  OK    {email} (role={role_name})")
        created += 1

    db.commit()
    print(f"Done: created={created}, skipped={skipped}")


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
