from typing import Sequence
from sqlalchemy.engine.result import Result
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.models import Device, TelemetryReading, DeviceStatus

class DeviceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> Sequence[Device]:
        result: Result[tuple[Device]] = await self.session.execute(select(Device))
        return result.scalars().all()

    async def get_device(self, device_id: int) -> Device | None:
        return await self.session.get(Device, device_id)

    async def create_device(self, hardware_id: str) -> Device | None:
        device = Device(hardware_id=hardware_id, status=DeviceStatus.PENDING)
        self.session.add(device)
        await self.session.flush()
        return device
    
    async def update_device_status(self, device_id: int, desired_status: DeviceStatus) -> Device | None:
        device: Device | None = await self.get_device(device_id)
        if device:
            device.status = desired_status
        return device

    async def get_or_create_device(self, hardware_id: str) -> Device:
        result = await self.session.execute(
            select(Device).where(Device.hardware_id == hardware_id)
        )
        device = result.scalar_one_or_none()

        if not device:
            device = Device(hardware_id=hardware_id, status=DeviceStatus.PENDING)
            self.session.add(device)
            await self.session.flush() # Get the ID without committing yet
        
        return device

    async def add_telemetry(self, device_id: int, data: dict, ts: datetime | None = None):
        """Unrolls a dictionary into individual TelemetryReading rows."""
        timestamp = ts or datetime.now(timezone.utc)
        readings = []
        
        for metric, value in data.items():
            if isinstance(value, (int, float)):
                readings.append(
                    TelemetryReading(
                        device_id=device_id,
                        metric=metric,
                        value=float(value),
                        timestamp=timestamp
                    )
                )
        
        if readings:
            self.session.add_all(readings)
