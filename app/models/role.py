from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255))

    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )
    users: Mapped[list[User]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255))

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions,
        back_populates="permissions",
    )


# Canonical permission strings used across the codebase.
# Roles are seeded with subsets of this list (see seeds/seed_roles.py).
class Permissions:
    STORE_READ = "store:read"
    STORE_CREATE = "store:create"
    STORE_UPDATE = "store:update"
    STORE_DELETE = "store:delete"
    STORE_IMPORT = "store:import"
    USER_MANAGE = "user:manage"


ALL_PERMISSIONS: tuple[str, ...] = (
    Permissions.STORE_READ,
    Permissions.STORE_CREATE,
    Permissions.STORE_UPDATE,
    Permissions.STORE_DELETE,
    Permissions.STORE_IMPORT,
    Permissions.USER_MANAGE,
)


# Role → permission mapping used by the seed script.
ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "admin": ALL_PERMISSIONS,
    "marketer": (
        Permissions.STORE_READ,
        Permissions.STORE_CREATE,
        Permissions.STORE_UPDATE,
        Permissions.STORE_DELETE,
        Permissions.STORE_IMPORT,
    ),
    "viewer": (Permissions.STORE_READ,),
}
