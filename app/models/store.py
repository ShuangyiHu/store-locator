from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StoreType(str, enum.Enum):
    FLAGSHIP = "flagship"
    REGULAR = "regular"
    OUTLET = "outlet"
    EXPRESS = "express"


class StoreStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TEMPORARILY_CLOSED = "temporarily_closed"


# Allowed service names — per requirements §4.1.
# Stored as rows in the `services` table (seeded once, never user-edited).
ALLOWED_SERVICES: tuple[str, ...] = (
    "pharmacy",
    "pickup",
    "returns",
    "optical",
    "photo_printing",
    "gift_wrapping",
    "automotive",
    "garden_center",
)


store_services = Table(
    "store_services",
    Base.metadata,
    Column(
        "store_id",
        String(10),
        ForeignKey("stores.store_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "service_id",
        Integer,
        ForeignKey("services.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    stores: Mapped[list[Store]] = relationship(
        secondary=store_services,
        back_populates="services",
    )


class Store(Base):
    __tablename__ = "stores"

    store_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    store_type: Mapped[StoreType] = mapped_column(
        SAEnum(
            StoreType,
            values_callable=lambda e: [m.value for m in e],
            name="store_type_enum",
        ),
        nullable=False,
    )
    status: Mapped[StoreStatus] = mapped_column(
        SAEnum(
            StoreStatus,
            values_callable=lambda e: [m.value for m in e],
            name="store_status_enum",
        ),
        nullable=False,
        default=StoreStatus.ACTIVE,
    )

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    address_street: Mapped[str] = mapped_column(String(255), nullable=False)
    address_city: Mapped[str] = mapped_column(String(100), nullable=False)
    address_state: Mapped[str] = mapped_column(String(2), nullable=False)
    address_postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    address_country: Mapped[str] = mapped_column(String(3), nullable=False, default="USA")

    phone: Mapped[str | None] = mapped_column(String(20))

    hours_mon: Mapped[str] = mapped_column(String(20), nullable=False)
    hours_tue: Mapped[str] = mapped_column(String(20), nullable=False)
    hours_wed: Mapped[str] = mapped_column(String(20), nullable=False)
    hours_thu: Mapped[str] = mapped_column(String(20), nullable=False)
    hours_fri: Mapped[str] = mapped_column(String(20), nullable=False)
    hours_sat: Mapped[str] = mapped_column(String(20), nullable=False)
    hours_sun: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    services: Mapped[list[Service]] = relationship(
        secondary=store_services,
        back_populates="stores",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_stores_lat_lon", "latitude", "longitude"),
        Index("ix_stores_status", "status"),
        Index("ix_stores_store_type", "store_type"),
        Index("ix_stores_postal_code", "address_postal_code"),
    )
