from app.infrastructure.service_factories import create_telemetry_service, create_device_service
from app.infrastructure.db import get_db_session
from app.infrastructure.repositories import DeviceRepository, TelemetryRepository
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.infrastructure.hardware.sense_hat_adapter import MockSenseHat, RealSenseHat
from app.infrastructure.hardware.base import SensorInterface

def get_sensor_adapter() -> SensorInterface:
    if settings.hardware_mode == "PROD":
        return RealSenseHat()
    return MockSenseHat()

def get_device_repo(session: AsyncSession = Depends(get_db_session)):
    return DeviceRepository(session)

def get_telemetry_repo(session: AsyncSession = Depends(get_db_session)):
    return TelemetryRepository(session)

async def get_telemetry_service(session: AsyncSession = Depends(get_db_session)):
    return create_telemetry_service(session)

async def get_device_service(session: AsyncSession = Depends(get_db_session)):
    return create_device_service(session)