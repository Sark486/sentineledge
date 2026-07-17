from app.domain.events import DeviceEvents
from app.domain.intervals import Interval, ONLINE_WINDOW, resolve_interval
from app.domain.sensors import EnvironmentalData
from app.infrastructure.models import ClimateReading, Device
from dataclasses import dataclass
from typing import Any, Sequence, Optional
from datetime import datetime, timedelta, timezone
from app.infrastructure.repositories import TelemetryRepository, DeviceRepository
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SeriesResult:
    interval: Interval
    requested: Interval | None
    downgraded: bool
    start: datetime
    end: datetime
    rows: Sequence[Any]


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

    async def save_telemetry(self, device_id: int, climate_data: EnvironmentalData, ts: datetime | None = None):
        device: Device | None = await self.device_repo.get_by_id(device_id)

        if not device:
            return

        location_name = await self.__get_location_name(device_id)

        await self.repo.add_telemetry(
            device_id=device_id,
            climate_data=climate_data,
            location_name=location_name,
            ts=ts or climate_data.timestamp
        )

    async def get_latest_telemetry_by_device(self, device_id: int) -> Sequence[ClimateReading]:
        return await self.repo.get_latest_telemetry(device_id)

    async def get_telemetry(
        self,
        device_id: Optional[int] = None,
        location: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, Sequence[ClimateReading]]:
        """
        Query climate readings with optional filters. Returns both total count and paginated results.

        Args:
            device_id: Filter by device ID
            location: Filter by location name
            start_date: Filter readings from this date onwards
            end_date: Filter readings up to this date
            limit: Maximum number of results
            offset: Number of results to skip for pagination

        Returns:
            Tuple of (total_count, results)
        """
        count = await self.repo.count_by_filters(
            device_id=device_id,
            location=location,
            start_date=start_date,
            end_date=end_date,
        )

        results = await self.repo.get_by_filters(
            device_id=device_id,
            location=location,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        return count, results

    async def get_series(
        self,
        interval: Optional[Interval] = None,
        device_id: Optional[int] = None,
        location: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> SeriesResult:
        """Pre-aggregated time-series, sourced from whichever table/view resolve_interval picks."""
        now = datetime.now(timezone.utc)
        end = end or now
        start = start or (end - timedelta(hours=24))

        resolved = resolve_interval(interval, start, end, now)
        rows = await self.repo.get_series(
            source=resolved.source,
            start=start,
            end=end,
            device_id=device_id,
            location=location,
        )

        return SeriesResult(
            interval=resolved.interval,
            requested=resolved.requested,
            downgraded=resolved.downgraded,
            start=start,
            end=end,
            rows=rows,
        )

    async def get_current_readings(self) -> Sequence[Any]:
        """Latest reading for each device currently online (reported within the online window)."""
        return await self.repo.get_current_readings(ONLINE_WINDOW)

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