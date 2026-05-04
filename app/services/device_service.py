from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.models import Device, DeviceStatus
from app.infrastructure.repositories import DeviceRepository

class DeviceService():
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.repo = DeviceRepository(db_session)

    async def list_devices(self) -> Sequence[Device]:
        return await self.repo.list_all()
    
    async def get_device(self, device_id: int) -> Device | None:
        return await self.repo.get_device(device_id)

    async def activate_device(self, device_id: int) -> Device | None:
        device: Device | None =  await self.repo.update_device_status(device_id, DeviceStatus.ACTIVE)
        await self.db_session.commit()
        return device
    
    async def block_device(self, device_id: int) -> Device | None:
        device: Device | None =  await self.repo.update_device_status(device_id, DeviceStatus.BLOCKED)
        await self.db_session.commit()
        return device