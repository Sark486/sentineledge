from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Any
from datetime import datetime
from app.infrastructure.db import get_db_session
from app.core.deps import get_sensor_adapter, get_telemetry_service
from app.domain.intervals import Interval
from app.domain.sensors import EnvironmentalData
from app.services.telemetry_service import TelemetryService
from app.api.schemas import ClimateReadingRead, CurrentReadingRead, PaginatedResponse, SeriesPoint, SeriesResponse

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])

@router.get("/current")
async def get_current_telemetry(
    adapter=Depends(get_sensor_adapter),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get current telemetry data from hardware sensor.
    """
    # Get data from hardware
    data: EnvironmentalData = adapter.read_data()
    
    # # Persist to TimescaleDB
    # repo = TelemetryRepository(db)
    # await repo.save_reading(data)
    
    return data

@router.get("", response_model=PaginatedResponse[ClimateReadingRead])
async def list_telemetry(
    device_id: Optional[int] = Query(None, description="Filter by device ID"),
    location: Optional[str] = Query(None, description="Filter by location name"),
    start_date: Optional[datetime] = Query(None, description="Start date for range filter (ISO 8601 format)"),
    end_date: Optional[datetime] = Query(None, description="End date for range filter (ISO 8601 format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    service: TelemetryService = Depends(get_telemetry_service),
) -> Any:
    """
    Get climate readings with optional filters.

    Query Parameters:
    - **device_id**: Filter by source device (device ID)
    - **location**: Filter by location name
    - **start_date**: Include readings from this date onwards (ISO 8601)
    - **end_date**: Include readings up to this date (ISO 8601)
    - **limit**: Maximum number of results (default: 100, max: 1000)
    - **offset**: Pagination offset (default: 0)

    Example: `/telemetry?device_id=1&start_date=2026-01-01&limit=50`
    """
    count, readings = await service.get_telemetry(
        device_id=device_id,
        location=location,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return PaginatedResponse(
        count=count,
        limit=limit,
        offset=offset,
        data=list(readings)
    )

@router.get("/series", response_model=SeriesResponse)
async def get_telemetry_series(
    interval: Optional[Interval] = Query(None, description="Requested bucket interval: 1m, 5m, or 1h. Omit to auto-pick from the range."),
    device_id: Optional[int] = Query(None, description="Filter by device ID"),
    location: Optional[str] = Query(None, description="Filter by location name"),
    start_date: Optional[datetime] = Query(None, description="Start of range (ISO 8601). Defaults to 24h before end_date"),
    end_date: Optional[datetime] = Query(None, description="End of range (ISO 8601). Defaults to now"),
    service: TelemetryService = Depends(get_telemetry_service),
) -> Any:
    """
    Get pre-aggregated climate time-series data, bucketed at a resolved interval.

    The effective interval is the requested `interval` (or a readability
    default based on the range) coarsened to whatever the retention
    policy still has data for. `downgraded` is true when the requested
    interval couldn't be honored because that source no longer retains
    data that old.

    Example: `/telemetry/series?interval=5m&device_id=1&start_date=2026-06-01`
    """
    result = await service.get_series(
        interval=interval,
        device_id=device_id,
        location=location,
        start=start_date,
        end=end_date,
    )

    return SeriesResponse(
        interval=result.interval.value,
        requested_interval=result.requested.value if result.requested else None,
        downgraded=result.downgraded,
        start=result.start,
        end=result.end,
        data=[SeriesPoint.model_validate(row) for row in result.rows],
    )

@router.get("/latest", response_model=list[CurrentReadingRead])
async def get_latest_readings(
    service: TelemetryService = Depends(get_telemetry_service),
) -> Any:
    """
    Get the latest reading for each device that is currently online
    (last reading within the online window), joined to its location.
    Offline devices are omitted.
    """
    rows = await service.get_current_readings()
    return [CurrentReadingRead.model_validate(row) for row in rows]

@router.get("/by-device/{device_id}", response_model=PaginatedResponse[ClimateReadingRead])
async def get_telemetry_by_device(
    device_id: int,
    start_date: Optional[datetime] = Query(None, description="Start date for range filter (ISO 8601 format)"),
    end_date: Optional[datetime] = Query(None, description="End date for range filter (ISO 8601 format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    service: TelemetryService = Depends(get_telemetry_service),
) -> Any:
    """
    Get climate readings for a specific device with optional filters.

    Path Parameters:
    - **device_id**: The device ID to fetch climate readings for

    Query Parameters:
    - **start_date**: Include readings from this date onwards (ISO 8601)
    - **end_date**: Include readings up to this date (ISO 8601)
    - **limit**: Maximum number of results (default: 100, max: 1000)
    - **offset**: Pagination offset (default: 0)
    """
    count, readings = await service.get_telemetry(
        device_id=device_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return PaginatedResponse(
        count=count,
        limit=limit,
        offset=offset,
        data=list(readings)
    )

@router.get("/by-location/{location}", response_model=PaginatedResponse[ClimateReadingRead])
async def get_telemetry_by_location(
    location: str,
    device_id: Optional[int] = Query(None, description="Filter by device ID"),
    start_date: Optional[datetime] = Query(None, description="Start date for range filter (ISO 8601 format)"),
    end_date: Optional[datetime] = Query(None, description="End date for range filter (ISO 8601 format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    service: TelemetryService = Depends(get_telemetry_service),
) -> Any:
    """
    Get climate readings for a specific location with optional filters.

    Path Parameters:
    - **location**: The location name to fetch climate readings for

    Query Parameters:
    - **device_id**: Filter by device ID
    - **start_date**: Include readings from this date onwards (ISO 8601)
    - **end_date**: Include readings up to this date (ISO 8601)
    - **limit**: Maximum number of results (default: 100, max: 1000)
    - **offset**: Pagination offset (default: 0)
    """
    count, readings = await service.get_telemetry(
        device_id=device_id,
        location=location,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return PaginatedResponse(
        count=count,
        limit=limit,
        offset=offset,
        data=list(readings)
    )

