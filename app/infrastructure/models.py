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

    readings: Mapped[list["TelemetryReading"]] = relationship(back_populates="device")
    location: Mapped["Location"] = relationship(back_populates="devices")
    

class TelemetryReading(Base):
    __tablename__ = "telemetry_data"

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    metric: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    location_snapshot: Mapped[str] = mapped_column(String, nullable=False)

    device: Mapped["Device"] = relationship(back_populates="readings")

class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    
    devices: Mapped[list["Device"]] = relationship(back_populates="location")