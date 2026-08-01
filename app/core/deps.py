from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.service_factories import create_device_service, create_telemetry_service
from app.infrastructure.db import get_db_session
from app.services.device_service import DeviceService
from app.services.telemetry_service import TelemetryService

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_telemetry_service(session: SessionDep) -> TelemetryService:
    return create_telemetry_service(session)


async def get_device_service(session: SessionDep) -> DeviceService:
    return create_device_service(session)


TelemetryServiceDep = Annotated[TelemetryService, Depends(get_telemetry_service)]
DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]
