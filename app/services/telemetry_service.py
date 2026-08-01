from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.devices import DEFAULT_LOCATION_NAME
from app.domain.intervals import ONLINE_WINDOW, Interval, resolve_interval
from app.domain.sensors import EnvironmentalData
from app.infrastructure.models import ClimateReading, Device
from app.infrastructure.repositories import DeviceRepository, TelemetryRepository


@dataclass
class SeriesResult:
    interval: Interval
    requested: Interval | None
    downgraded: bool
    start: datetime
    end: datetime
    rows: Sequence[Any]


class TelemetryService:

    def __init__(self, repo: TelemetryRepository, device_repo: DeviceRepository):
        self.repo = repo
        self.device_repo = device_repo

    async def save_telemetry(
        self, device_id: int, climate_data: EnvironmentalData, ts: datetime | None = None
    ) -> None:
        device: Device | None = await self.device_repo.get_by_id(device_id)

        if not device:
            return

        # Denormalised at write time so a reading keeps the location it was
        # actually taken in, even after the device moves.
        location_name = device.location.display_name if device.location else DEFAULT_LOCATION_NAME

        await self.repo.add_telemetry(
            device_id=device_id,
            climate_data=climate_data,
            location_name=location_name,
            ts=ts,
        )

    async def get_latest_telemetry_by_device(self, device_id: int) -> Sequence[ClimateReading]:
        return await self.repo.get_latest_telemetry(device_id)

    async def get_telemetry(
        self,
        device_id: int | None = None,
        location: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, Sequence[ClimateReading]]:
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
        interval: Interval | None = None,
        device_id: int | None = None,
        location: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> SeriesResult:
        """Pre-aggregated time-series, sourced from whichever table/view resolve_interval picks."""
        now = datetime.now(UTC)
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
