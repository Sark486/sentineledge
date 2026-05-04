from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db import get_db_session
from app.core.deps import get_sensor_adapter
from app.domain.sensors import EnvironmentalData


router = APIRouter()

@router.get("/current")
async def get_current_telemetry(
    adapter=Depends(get_sensor_adapter),
    db: AsyncSession = Depends(get_db_session)
):
    # 1. Get data from hardware
    data: EnvironmentalData = adapter.read_data()
    
    # # 2. Persist to TimescaleDB
    # repo = TelemetryRepository(db)
    # await repo.save_reading(data)
    
    return data