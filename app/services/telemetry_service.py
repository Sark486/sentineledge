from app.domain.events import DeviceEvents
from app.infrastructure.models import TelemetryReading, Device
from typing import Sequence
from datetime import datetime
from app.infrastructure.repositories import TelemetryRepository, DeviceRepository
from sqlalchemy.ext.asyncio import AsyncSession
class TelemetryService:
    _location_cache: dict[int, str] = {}

    def __init__(self, session: AsyncSession, repo: TelemetryRepository, device_repo: DeviceRepository):
        self.session: AsyncSession = session
        self.repo = repo
        self.device_repo = device_repo
        DeviceEvents.subscribe_to_update(TelemetryService.invalidate_location_cache)

    @classmethod
    def invalidate_location_cache(cls, device_id: int):
        cls._location_cache.pop(device_id, None)

    async def save_telemetry(self, device_id: int, data: dict, ts: datetime | None = None):
        device: Device | None = await self.device_repo.get_by_id(device_id)
    
        if not device:
            # Handle the case where telemetry comes from an unknown device
            return

        location_name = await self.__get_location_name(device_id)

        await self.repo.add_telemetry(
            device_id=device_id, 
            data=data, 
            location_name=location_name, 
            ts=ts
        )

    async def get_latest_telemetry_by_device(self, device_id: int) -> Sequence[TelemetryReading]:
        return await self.repo.get_latest_telemetry(device_id)
    
    async def __get_location_name(self, device_id: int) -> str:
        """
        Internal helper to get location. 
        Tries cache first, falls back to DB if missing.
        """
        if device_id in self._location_cache:
            return self._location_cache[device_id]

        device = await self.device_repo.get_by_id(device_id)
        
        location_name = "Unassigned"
        if device and device.location:
            location_name = device.location.display_name
            
        # 3. Update cache for next time
        self._location_cache[device_id] = location_name
        return location_name