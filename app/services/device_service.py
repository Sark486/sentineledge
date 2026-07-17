from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.models import Device
from app.infrastructure.repositories import DeviceRepository, LocationRepository
from app.api.schemas import DeviceUpdate

class DeviceService():
    def __init__(self, db_session: AsyncSession, repo: DeviceRepository, location_repo: LocationRepository):
        self.db_session = db_session
        self.repo = repo
        self.location_repo = location_repo

    async def list_devices(self) -> Sequence[Device]:
        return await self.repo.list_all()

    async def count_devices(self) -> int:
        return await self.repo.count_all()
    
    async def get_device_by_id(self, device_id: int) -> Device | None:
        return await self.repo.get_by_id(device_id)

    async def create_device(self, hardware_id: str, location_id: int) -> Device:
        device: Device = await self.repo.create(hardware_id, location_id    =location_id)
        if device:
            await self.db_session.commit()
        return device

    async def get_or_create_device(self, hardware_id: str) -> Device:
        device = await self.repo.get_by_hardware_id(hardware_id)
        location_name = "Unknown"
        location = await self.location_repo.get_by_display_name(location_name)
        if not location:
            location = await self.location_repo.create(name=location_name)
        if not device:
            device = await self.create_device(hardware_id, location_id=location.id)
        return device

    async def update_device(self, device_id: int, schema: DeviceUpdate):
        update_data = schema.model_dump(exclude_unset=True)
        if "location_name" in update_data:
            loc_name = update_data.pop("location_name")
            location = await self.location_repo.get_or_create(loc_name)
            update_data["location_id"] = location.id
    
        device: Device | None = await self.repo.update(device_id, update_data)
        
        if device and update_data:
            await self.db_session.commit()
        
        await self.db_session.refresh(device)
        return device

    async def mark_online(self, device_id: int):
        device = await self.repo.get_by_id(device_id)
        if not device:
            return

        # Only update and commit if the last_seen is older than 300 seconds
        now = datetime.now(timezone.utc)
        if device.last_seen is None or (now - device.last_seen).total_seconds() > 300:
            device.is_online = True
            device.last_seen = now
            await self.db_session.commit() # Commit only happens occasionally
        else:
            pass
    