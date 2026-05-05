from sqlalchemy.orm import joinedload
from typing import Sequence
from sqlalchemy.engine.result import Result
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.models import Device, TelemetryReading, DeviceStatus, Location

class DeviceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> Sequence[Device]:
        query = (
            select(Device)
            .options(joinedload(Device.location))

        )
        result: Result[tuple[Device]] = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_id(self, device_id: int) -> Device | None:
        query = (
            select(Device)
            .filter(Device.id == device_id)
            .options(joinedload(Device.location))
        )        
        result: Result[tuple[Device]] = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_hardware_id(self, hardware_id: str) -> Device | None:
        result: Result[tuple[Device]] = await self.session.execute(
            select(Device).where(Device.hardware_id == hardware_id)
        )
        return result.scalar_one_or_none()

    async def create(self, hardware_id: str, location_id: int) -> Device:
        device = Device(hardware_id=hardware_id, location_id=location_id, status=DeviceStatus.PENDING)
        self.session.add(device)
        await self.session.flush()
        return device
    
    async def update(self, device_id: int, data: dict) -> Device | None:
        device: Device | None = await self.get_by_id(device_id)
        
        if device:
            for key, value in data.items():
                setattr(device, key, value)
        await self.session.flush()
        return device

class TelemetryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_telemetry(self, device_id: int, data: dict, location_name: str, ts: datetime | None = None) -> TelemetryReading | None:
        timestamp = ts or datetime.now(timezone.utc)
        readings = []
        
        for metric, value in data.items():
            if isinstance(value, (int, float)):
                readings.append(
                    TelemetryReading(
                        device_id=device_id,
                        metric=metric,
                        value=float(value),
                        location_snapshot=location_name,
                        timestamp=timestamp
                    )
                )
        
        if readings:
            self.session.add_all(readings)
            await self.session.flush()

    
    async def get_latest_telemetry(self, device_id: int) -> Sequence[TelemetryReading]:
        subquery = (
            select(TelemetryReading.timestamp)
            .where(TelemetryReading.device_id == device_id)
            .order_by(TelemetryReading.timestamp.desc())
            .limit(1)
            .scalar_subquery()
        )
        
        result = await self.session.execute(
            select(TelemetryReading).where(
                TelemetryReading.device_id == device_id,
                TelemetryReading.timestamp == subquery
            )
        )
        return result.scalars().all()

class LocationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> Sequence[Location]:
        result: Result[tuple[Location]] = await self.session.execute(select(Location))
        return result.scalars().all()

    async def get_by_id(self, location_id: int) -> Location | None:
        result: Result[tuple[Location]] = await self.session.execute(
            select(Location).where(Location.id == location_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_display_name(self, display_name: str) -> Location | None:
        result: Result[tuple[Location]] = await self.session.execute(
            select(Location).where(Location.display_name == display_name)
        )
        return result.scalar_one_or_none()

    async def create(self, name: str) -> Location:
        location = Location(display_name=name)
        self.session.add(location)
        await self.session.flush()
        return location

    async def get_or_create(self, name: str) -> Location:
        location = await self.get_by_display_name(name)
        if not location:
            location = await self.create(name)
        return location