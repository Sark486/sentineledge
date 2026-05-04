from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db import get_db_session
from app.infrastructure.models import TelemetryReading
from app.services.device_service import DeviceService
from app.exceptions.sentinet_not_found_error import SentinelNotFoundError
from app.infrastructure.models import Device

router = APIRouter(prefix="/devices", tags=["Devices"])

@router.get("/")
async def list_devices(db: AsyncSession = Depends(get_db_session)):
    service = DeviceService(db)
    return await service.list_devices()

@router.get("/{device_id}")
async def get_device(device_id: int, db: AsyncSession = Depends(get_db_session)) -> Device:
    service = DeviceService(db)
    device = await service.get_device(device_id)
    if not device:
        raise SentinelNotFoundError
    return device

@router.patch("/{device_id}/activate")
async def activate_device(device_id: int, db: AsyncSession = Depends(get_db_session)):
    service = DeviceService(db)
    device = await service.activate_device(device_id)
    if not device:
        raise SentinelNotFoundError
    return {"message": f"Device {device.hardware_id} is now ACTIVE"}

@router.patch("/{device_id}/block")
async def block_device(device_id: int, db: AsyncSession = Depends(get_db_session)):
    service = DeviceService(db)
    device = await service.block_device(device_id)
    if not device:
        raise SentinelNotFoundError
    return {"message": f"Device {device.hardware_id} is now BLOCKED"}

@router.get("/{device_id}/latest")
async def get_latest_data(device_id: int, db: AsyncSession = Depends(get_db_session)):
    subquery = (
        select(TelemetryReading.timestamp)
        .where(TelemetryReading.device_id == device_id)
        .order_by(TelemetryReading.timestamp.desc())
        .limit(1)
        .scalar_subquery()
    )
    
    result = await db.execute(
        select(TelemetryReading).where(
            TelemetryReading.device_id == device_id,
            TelemetryReading.timestamp == subquery
        )
    )
    return result.scalars().all()