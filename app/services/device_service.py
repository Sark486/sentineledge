from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DeviceUpdate
from app.domain.devices import DEFAULT_LOCATION_NAME, LIVENESS_REFRESH
from app.infrastructure.models import Device
from app.infrastructure.repositories import DeviceRepository, LocationRepository


class DeviceService:

    def __init__(
        self, session: AsyncSession, repo: DeviceRepository, location_repo: LocationRepository
    ):
        self.session = session
        self.repo = repo
        self.location_repo = location_repo

    async def list_devices(self) -> Sequence[Device]:
        return await self.repo.list_all()

    async def get_device_by_id(self, device_id: int) -> Device | None:
        return await self.repo.get_by_id(device_id)

    async def create_device(self, hardware_id: str, location_id: int) -> Device:
        return await self.repo.create(hardware_id, location_id=location_id)

    async def get_or_create_device(self, hardware_id: str) -> Device:
        device = await self.repo.get_by_hardware_id(hardware_id)
        if device:
            return device

        location = await self.location_repo.get_or_create(DEFAULT_LOCATION_NAME)
        return await self.create_device(hardware_id, location_id=location.id)

    async def update_device(self, device_id: int, schema: DeviceUpdate) -> Device | None:
        update_data = schema.model_dump(exclude_unset=True)

        location_name = update_data.pop("location_name", None)
        if location_name is not None:
            location = await self.location_repo.get_or_create(location_name)
            update_data["location_id"] = location.id

        device: Device | None = await self.repo.update(device_id, update_data)

        if device is None:
            return None

        if update_data:
            await self.session.commit()
            device = await self.repo.get_by_id(device_id)

        return device

    async def mark_online(self, device_id: int) -> None:
        device = await self.repo.get_by_id(device_id)
        if not device:
            return

        now = datetime.now(UTC)
        if device.last_seen is None or now - device.last_seen > LIVENESS_REFRESH:
            device.last_seen = now
