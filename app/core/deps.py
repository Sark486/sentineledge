from app.infrastructure.service_factories import create_telemetry_service, create_device_service
from app.infrastructure.db import get_db_session
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_telemetry_service(session: AsyncSession = Depends(get_db_session)):
    return create_telemetry_service(session)

async def get_device_service(session: AsyncSession = Depends(get_db_session)):
    return create_device_service(session)