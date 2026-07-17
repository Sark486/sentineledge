import enum
from datetime import datetime
from sqlalchemy import String, Float, DateTime, Boolean, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.infrastructure.db import Base

class DeviceStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"

class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    hardware_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    status: Mapped[DeviceStatus] = mapped_column(Enum(DeviceStatus), default=DeviceStatus.PENDING)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    readings: Mapped[list["ClimateReading"]] = relationship(back_populates="device")
    location: Mapped["Location"] = relationship(back_populates="devices")


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    
    devices: Mapped[list["Device"]] = relationship(back_populates="location")


class ClimateDataMixin:
    """Shared columns for all climate entities."""
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=True)
    humidity: Mapped[float] = mapped_column(Float, nullable=True)
    pressure: Mapped[float] = mapped_column(Float, nullable=True)
    location_snapshot: Mapped[str] = mapped_column(String, nullable=False)

class ClimateReading(Base, ClimateDataMixin):
    """The raw hypertable."""
    __tablename__ = "climate_readings"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    device: Mapped["Device"] = relationship(back_populates="readings")

class ClimateAggregateView(ClimateDataMixin, Base):
    """The generic view for all continuous aggregates."""
    __abstract__ = True  # SQLAlchemy will not create a table for this
    
    # In aggregates, 'timestamp' is technically called 'bucket'
    # We map 'timestamp' to 'bucket' so the API sees a consistent interface
    timestamp: Mapped[datetime] = mapped_column("bucket", DateTime(timezone=True), primary_key=True)
    
    # Ensure device_id is part of PK
    device_id: Mapped[int] = mapped_column(primary_key=True)

class Climate5mView(ClimateAggregateView):
    __tablename__ = "climate_5m"
    # Backed by a materialized view created via raw SQL in migrations, not a
    # real table. Excluded from Alembic autogenerate diffing in migrations/env.py
    # (include_object) so it's never proposed as CREATE/DROP TABLE.
    __table_args__ = {"info": {"skip_autogenerate": True}}

class Climate1hView(ClimateAggregateView):
    __tablename__ = "climate_1h"
    __table_args__ = {"info": {"skip_autogenerate": True}}