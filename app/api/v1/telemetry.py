from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.schemas import (
    ClimateReadingRead,
    CurrentReadingRead,
    PaginatedResponse,
    SeriesPoint,
    SeriesResponse,
)
from app.core.deps import TelemetryServiceDep
from app.domain.intervals import Interval
from app.services.telemetry_service import TelemetryService

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])

DeviceIdQuery = Annotated[int | None, Query(description="Filter by device ID")]
LocationQuery = Annotated[str | None, Query(description="Filter by location name")]
StartDateQuery = Annotated[
    datetime | None, Query(description="Start date for range filter (ISO 8601 format)")
]
EndDateQuery = Annotated[
    datetime | None, Query(description="End date for range filter (ISO 8601 format)")
]
LimitQuery = Annotated[int, Query(ge=1, le=1000, description="Maximum number of results")]
OffsetQuery = Annotated[int, Query(ge=0, description="Number of results to skip")]


def _as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive query datetime.

    `?start_date=2026-06-01` parses without a timezone, and every timestamp
    downstream - the domain's range arithmetic and the `timestamptz` columns -
    is aware. Reading a bare date as UTC keeps the two comparable.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def _paginated_readings(
    service: TelemetryService,
    *,
    device_id: int | None,
    location: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
    limit: int,
    offset: int,
) -> PaginatedResponse:
    """Shared body of the three list endpoints, which differ only in how the
    device/location filter is supplied (query string vs path segment)."""
    count, readings = await service.get_telemetry(
        device_id=device_id,
        location=location,
        start_date=_as_utc(start_date),
        end_date=_as_utc(end_date),
        limit=limit,
        offset=offset,
    )

    return PaginatedResponse(
        count=count,
        limit=limit,
        offset=offset,
        data=[ClimateReadingRead.model_validate(reading) for reading in readings],
    )


@router.get("", response_model=PaginatedResponse[ClimateReadingRead])
async def list_telemetry(
    service: TelemetryServiceDep,
    device_id: DeviceIdQuery = None,
    location: LocationQuery = None,
    start_date: StartDateQuery = None,
    end_date: EndDateQuery = None,
    limit: LimitQuery = 100,
    offset: OffsetQuery = 0,
) -> PaginatedResponse:
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
    return await _paginated_readings(
        service,
        device_id=device_id,
        location=location,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get("/series", response_model=SeriesResponse)
async def get_telemetry_series(
    service: TelemetryServiceDep,
    interval: Annotated[
        Interval | None,
        Query(
            description=(
                "Requested bucket interval: 1m, 5m, or 1h. "
                "Omit to auto-pick from the range."
            )
        ),
    ] = None,
    device_id: DeviceIdQuery = None,
    location: LocationQuery = None,
    start_date: Annotated[
        datetime | None,
        Query(description="Start of range (ISO 8601). Defaults to 24h before end_date"),
    ] = None,
    end_date: Annotated[
        datetime | None, Query(description="End of range (ISO 8601). Defaults to now")
    ] = None,
) -> SeriesResponse:
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
        start=_as_utc(start_date),
        end=_as_utc(end_date),
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
async def get_latest_readings(service: TelemetryServiceDep) -> list[CurrentReadingRead]:
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
    service: TelemetryServiceDep,
    location: LocationQuery = None,
    start_date: StartDateQuery = None,
    end_date: EndDateQuery = None,
    limit: LimitQuery = 100,
    offset: OffsetQuery = 0,
) -> PaginatedResponse:
    """
    Get climate readings for a specific device with optional filters.

    Path Parameters:
    - **device_id**: The device ID to fetch climate readings for

    Query Parameters:
    - **location**: Filter by location name
    - **start_date**: Include readings from this date onwards (ISO 8601)
    - **end_date**: Include readings up to this date (ISO 8601)
    - **limit**: Maximum number of results (default: 100, max: 1000)
    - **offset**: Pagination offset (default: 0)
    """
    return await _paginated_readings(
        service,
        device_id=device_id,
        location=location,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get("/by-location/{location}", response_model=PaginatedResponse[ClimateReadingRead])
async def get_telemetry_by_location(
    location: str,
    service: TelemetryServiceDep,
    device_id: DeviceIdQuery = None,
    start_date: StartDateQuery = None,
    end_date: EndDateQuery = None,
    limit: LimitQuery = 100,
    offset: OffsetQuery = 0,
) -> PaginatedResponse:
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
    return await _paginated_readings(
        service,
        device_id=device_id,
        location=location,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
