from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Result, Row, and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.domain.sensors import EnvironmentalData
from app.infrastructure.models import (
    Climate1hView,
    Climate5mView,
    ClimateReading,
    Device,
    DeviceStatus,
    Location,
)

# Only the continuous aggregates: the raw table takes the bucketing branch in
# get_series and never reaches this lookup.
_AGGREGATE_MODEL: dict[str, Any] = {
    "climate_5m": Climate5mView,
    "climate_1h": Climate1hView,
}

# The only columns a PATCH is allowed to reach. The repository assigns whatever
# it is handed, so the whitelist is what keeps a rogue key out of the model.
_UPDATABLE_DEVICE_FIELDS = frozenset({"display_name", "status", "location_id"})


class DeviceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> Sequence[Device]:
        query = select(Device).options(joinedload(Device.location))
        result: Result[tuple[Device]] = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_id(self, device_id: int) -> Device | None:
        query = (
            select(Device)
            .where(Device.id == device_id)
            .options(joinedload(Device.location))
        )
        result: Result[tuple[Device]] = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_hardware_id(self, hardware_id: str) -> Device | None:
        result: Result[tuple[Device]] = await self.session.execute(
            select(Device).where(Device.hardware_id == hardware_id)
        )
        return result.scalar_one_or_none()

    async def create(self, hardware_id: str, location_id: int) -> Device:
        device = Device(
            hardware_id=hardware_id, location_id=location_id, status=DeviceStatus.PENDING
        )
        self.session.add(device)
        await self.session.flush()
        return device

    async def update(self, device_id: int, data: dict) -> Device | None:
        device: Device | None = await self.get_by_id(device_id)
        if device is None:
            return None

        for key, value in data.items():
            if key not in _UPDATABLE_DEVICE_FIELDS:
                raise ValueError(f"{key!r} is not an updatable device field")
            setattr(device, key, value)

        await self.session.flush()
        return device


class TelemetryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_telemetry(
        self,
        device_id: int,
        climate_data: EnvironmentalData,
        location_name: str,
        ts: datetime | None = None,
    ) -> ClimateReading:
        reading = ClimateReading(
            device_id=device_id,
            temperature=climate_data.temperature,
            humidity=climate_data.humidity,
            pressure=climate_data.pressure,
            location_snapshot=location_name,
            timestamp=ts or climate_data.timestamp,
        )
        self.session.add(reading)
        await self.session.flush()
        return reading

    async def get_latest_telemetry(self, device_id: int) -> Sequence[ClimateReading]:
        subquery = (
            select(ClimateReading.timestamp)
            .where(ClimateReading.device_id == device_id)
            .order_by(ClimateReading.timestamp.desc())
            .limit(1)
            .scalar_subquery()
        )

        result = await self.session.execute(
            select(ClimateReading).where(
                ClimateReading.device_id == device_id,
                ClimateReading.timestamp == subquery,
            )
        )
        return result.scalars().all()

    @staticmethod
    def _filters(
        model: Any,
        device_id: int | None = None,
        location: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[ColumnElement[bool]]:
        """The filter set shared by the page, its count, and the series queries.

        Built in one place so a page and its total can never disagree about
        which rows they describe.
        """
        filters: list[ColumnElement[bool]] = []
        if device_id is not None:
            filters.append(model.device_id == device_id)
        if location is not None:
            filters.append(model.location_snapshot == location)
        if start_date is not None:
            filters.append(model.timestamp >= start_date)
        if end_date is not None:
            filters.append(model.timestamp <= end_date)
        return filters

    async def get_by_filters(
        self,
        device_id: int | None = None,
        location: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ClimateReading]:
        query = select(ClimateReading).options(
            joinedload(ClimateReading.device).joinedload(Device.location)
        )

        filters = self._filters(ClimateReading, device_id, location, start_date, end_date)
        if filters:
            query = query.where(and_(*filters))

        query = query.order_by(ClimateReading.timestamp.desc()).limit(limit).offset(offset)

        result: Result[tuple[ClimateReading]] = await self.session.execute(query)
        return result.scalars().unique().all()

    async def count_by_filters(
        self,
        device_id: int | None = None,
        location: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        query = select(func.count(ClimateReading.timestamp))

        filters = self._filters(ClimateReading, device_id, location, start_date, end_date)
        if filters:
            query = query.where(and_(*filters))

        result: Result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_series(
        self,
        source: str,
        start: datetime,
        end: datetime,
        device_id: int | None = None,
        location: str | None = None,
    ) -> Sequence[Row]:
        """
        One row per (bucket, device) for the given source table/view.

        `climate_readings` is bucketed to a clean 1-minute grid here (raw
        cadence may be sub-minute); `climate_5m`/`climate_1h` are continuous
        aggregates already grouped by (bucket, device_id, location_snapshot),
        so they're selected straight with no re-aggregation.
        """
        if source == "climate_readings":
            bucket = func.time_bucket(
                text("interval '1 minute'"), ClimateReading.timestamp
            ).label("timestamp")
            query = select(
                bucket,
                ClimateReading.device_id,
                func.avg(ClimateReading.temperature).label("temperature"),
                func.avg(ClimateReading.humidity).label("humidity"),
                func.avg(ClimateReading.pressure).label("pressure"),
            )

            filters = self._filters(ClimateReading, device_id, location, start, end)
            query = (
                query.where(and_(*filters))
                .group_by(bucket, ClimateReading.device_id)
                .order_by(bucket.asc(), ClimateReading.device_id)
            )
        else:
            model = _AGGREGATE_MODEL[source]
            query = select(
                model.timestamp,
                model.device_id,
                model.temperature,
                model.humidity,
                model.pressure,
            )

            filters = self._filters(model, device_id, location, start, end)
            query = query.where(and_(*filters)).order_by(model.timestamp.asc(), model.device_id)

        result = await self.session.execute(query)
        return result.all()

    async def get_current_readings(self, window: timedelta) -> Sequence[Row]:
        """Latest reading per device that reported within `window`, joined to device/location."""
        cutoff = datetime.now(UTC) - window

        query = (
            select(
                ClimateReading.device_id,
                Device.display_name,
                Location.display_name.label("location"),
                ClimateReading.timestamp,
                ClimateReading.temperature,
                ClimateReading.humidity,
                ClimateReading.pressure,
            )
            .join(Device, Device.id == ClimateReading.device_id)
            .outerjoin(Location, Location.id == Device.location_id)
            .where(ClimateReading.timestamp >= cutoff)
            .distinct(ClimateReading.device_id)
            .order_by(ClimateReading.device_id, ClimateReading.timestamp.desc())
        )

        result = await self.session.execute(query)
        return result.all()


class LocationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_display_name(self, display_name: str) -> Location | None:
        result: Result[tuple[Location]] = await self.session.execute(
            select(Location).where(Location.display_name == display_name)
        )
        return result.scalar_one_or_none()

    async def create(self, name: str) -> Location:
        location = Location(display_name=name)
        self.session.add(location)
        await self.session.flush()
        return location

    async def get_or_create(self, name: str) -> Location:
        location = await self.get_by_display_name(name)
        if not location:
            location = await self.create(name)
        return location
