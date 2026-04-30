"""User CRUD for admin endpoints."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.role import Role
from app.models.user import User, UserStatus
from app.schemas.user import UserCreate, UserUpdate


class DuplicateEmailError(Exception):
    pass


class InvalidRoleError(Exception):
    pass


class CannotModifySelfError(Exception):
    """Admin tried to deactivate or change their own account via admin API."""


def _role_by_name(db: Session, name: str) -> Role:
    role = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
    if role is None:
        raise InvalidRoleError(f"role '{name}' does not exist")
    return role


def create_user(db: Session, payload: UserCreate) -> User:
    email = str(payload.email).lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise DuplicateEmailError(email)

    role = _role_by_name(db, payload.role)
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role_id=role.id,
        status=UserStatus.ACTIVE,
        must_change_password=True,  # admin-provisioned → must rotate
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def list_users(db: Session, page: int, page_size: int) -> tuple[list[User], int]:
    base = select(User)
    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    items = db.execute(
        base.order_by(User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    return list(items), int(total)


def update_user(
    db: Session,
    user_id: int,
    payload: UserUpdate,
    actor: User,
) -> User | None:
    user = db.get(User, user_id)
    if user is None:
        return None

    data = payload.model_dump(exclude_unset=True)

    # Self-modification guard: admin cannot lock themselves out of admin role
    # or deactivate their own account via admin API.
    if user.id == actor.id:
        if "role" in data and data["role"] != user.role.name:
            raise CannotModifySelfError("cannot change your own role")
        if "status" in data and data["status"] != user.status.value:
            raise CannotModifySelfError("cannot change your own status")

    if "role" in data:
        new_role = _role_by_name(db, data["role"])
        user.role_id = new_role.id
    if "status" in data:
        user.status = UserStatus(data["status"])

    db.commit()
    db.refresh(user)
    return user


def soft_delete_user(db: Session, user_id: int, actor: User) -> bool:
    user = db.get(User, user_id)
    if user is None:
        return False
    if user.id == actor.id:
        raise CannotModifySelfError("cannot deactivate yourself")

    user.status = UserStatus.INACTIVE
    # Revoke all of this user's refresh tokens — locks them out immediately
    for token in user.refresh_tokens:
        token.revoked = True
    db.commit()
    return True
