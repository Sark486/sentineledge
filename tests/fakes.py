"""Test doubles for the async SQLAlchemy session and the repository layer.

Two levels of substitution are used across the suite:

* `FakeSession` replaces `AsyncSession` for repository tests. It records the
  statements it is handed so tests can assert on the compiled SQL, and it hands
  back queued `FakeResult`s instead of talking to Postgres.
* The `Fake*Repository` classes replace the repositories for service tests, so
  service behaviour (caching, commit policy, lifecycle branching) is exercised
  without any SQL at all.

Neither kind of double subclasses what it replaces — inheriting `AsyncSession`
would drag in the machinery these tests exist to avoid. They are structural
stand-ins, so `stands_in_for` narrows them to the declared type at the one point
where they cross into production code that is annotated for the real thing.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.sensors import EnvironmentalData
from app.infrastructure.models import ClimateReading, Device, DeviceStatus, Location
from app.infrastructure.repositories import (
    DeviceRepository,
    LocationRepository,
    TelemetryRepository,
)

# Typed as Any so it can stand in as a default for any annotated parameter.
_UNSET: Any = object()

def stands_in_for[T](_declared: type[T], double: object) -> T:
    """Narrow a test double to the type the production signature declares.

    `stands_in_for(AsyncSession, FakeSession())` reads as the assertion it is:
    this object covers the part of `AsyncSession` the code under test uses.
    """
    return cast(T, double)


def as_session(double: object) -> AsyncSession:
    return stands_in_for(AsyncSession, double)


def device_repository(session: "FakeSession") -> DeviceRepository:
    return DeviceRepository(as_session(session))


def telemetry_repository(session: "FakeSession") -> TelemetryRepository:
    return TelemetryRepository(as_session(session))


def location_repository(session: "FakeSession") -> LocationRepository:
    return LocationRepository(as_session(session))


# --------------------------------------------------------------------------- #
# Session / result doubles
# --------------------------------------------------------------------------- #


class FakeScalars:
    def __init__(self, rows: Sequence[Any]):
        self._rows = list(rows)

    def all(self) -> list[Any]:
        return list(self._rows)

    def unique(self) -> "FakeScalars":
        return self

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class FakeResult:
    """Covers only the `Result` accessors the repositories actually call."""

    def __init__(self, rows: Sequence[Any] = (), scalar: Any = _UNSET):
        self._rows = list(rows)
        self._scalar = scalar

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._rows)

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar(self) -> Any:
        if self._scalar is not _UNSET:
            return self._scalar
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any:
        if len(self._rows) > 1:
            raise AssertionError("scalar_one_or_none() on multiple rows")
        return self._rows[0] if self._rows else None


class FakeSession:
    """Stand-in for `AsyncSession`.

    Pass `results` to queue up the values `execute()` returns, in call order; an
    exhausted queue yields an empty `FakeResult`.
    """

    def __init__(self, results: Sequence[FakeResult] | None = None):
        self.results = list(results or [])
        self.executed: list[Any] = []
        self.added: list[Any] = []
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0
        self.refreshed: list[Any] = []
        self.closed = False

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> FakeResult:
        self.executed.append(statement)
        if self.results:
            return self.results.pop(0)
        return FakeResult()

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, instance: Any, *args: Any, **kwargs: Any) -> None:
        if instance is None:
            # Mirrors SQLAlchemy, which raises UnmappedInstanceError on None.
            raise ValueError("refresh() called with None")
        self.refreshed.append(instance)

    async def close(self) -> None:
        self.closed = True

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        self.closed = True
        return False

    # -- assertion helpers -------------------------------------------------- #

    @property
    def last_statement(self) -> Any:
        return self.executed[-1]

    def sql(self, index: int = -1) -> str:
        """The statement compiled against the Postgres dialect, whitespace-normalised."""
        compiled = self.executed[index].compile(dialect=postgresql.dialect())
        return " ".join(str(compiled).split())

    def params(self, index: int = -1) -> dict[str, Any]:
        return dict(self.executed[index].compile(dialect=postgresql.dialect()).params)


class FakeSessionMaker:
    """Replacement for `async_session_maker`: returns the same session every call."""

    def __init__(self, session: FakeSession):
        self.session = session
        self.calls = 0

    def __call__(self) -> FakeSession:
        self.calls += 1
        return self.session


# --------------------------------------------------------------------------- #
# Model builders
# --------------------------------------------------------------------------- #


def make_location(location_id: int = 1, display_name: str = "Kitchen") -> Location:
    return Location(id=location_id, display_name=display_name)


def make_device(
    device_id: int = 1,
    hardware_id: str = "pi-01",
    display_name: str | None = "Kitchen Pi",
    status: DeviceStatus = DeviceStatus.ACTIVE,
    location: Location | None = _UNSET,  # type: ignore[assignment]
    last_seen: datetime | None = None,
) -> Device:
    if location is _UNSET:
        location = make_location()
    device = Device(
        id=device_id,
        hardware_id=hardware_id,
        display_name=display_name,
        status=status,
        last_seen=last_seen,
    )
    if location is not None:
        device.location = location
    device.location_id = location.id if location else None
    return device


def make_reading(
    device_id: int = 1,
    temperature: float | None = 21.5,
    humidity: float | None = 44.0,
    pressure: float | None = 1013.2,
    location_snapshot: str = "Kitchen",
    timestamp: datetime | None = None,
) -> ClimateReading:
    return ClimateReading(
        id=1,
        device_id=device_id,
        temperature=temperature,
        humidity=humidity,
        pressure=pressure,
        location_snapshot=location_snapshot,
        timestamp=timestamp or datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
    )


def make_climate_data(
    temperature: float = 21.5,
    humidity: float = 44.0,
    pressure: float = 1013.2,
    source: str = "pi-01",
    timestamp: datetime | None = None,
) -> EnvironmentalData:
    return EnvironmentalData(
        temperature=temperature,
        humidity=humidity,
        pressure=pressure,
        source=source,
        timestamp=timestamp or datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
    )


# --------------------------------------------------------------------------- #
# Repository doubles
# --------------------------------------------------------------------------- #


class FakeDeviceRepository:
    def __init__(self, devices: Sequence[Device] = (), create_returns: Any = _UNSET):
        self.devices: list[Device] = list(devices)
        self.created: list[tuple[str, int]] = []
        self.updates: list[tuple[int, dict]] = []
        self.get_by_id_calls: list[int] = []
        self._create_returns = create_returns
        self._next_id = max((d.id for d in self.devices), default=0) + 1

    async def list_all(self) -> Sequence[Device]:
        return list(self.devices)

    async def get_by_id(self, device_id: int) -> Device | None:
        self.get_by_id_calls.append(device_id)
        return next((d for d in self.devices if d.id == device_id), None)

    async def get_by_hardware_id(self, hardware_id: str) -> Device | None:
        return next((d for d in self.devices if d.hardware_id == hardware_id), None)

    async def create(self, hardware_id: str, location_id: int) -> Device:
        self.created.append((hardware_id, location_id))
        if self._create_returns is not _UNSET:
            return self._create_returns
        device = make_device(
            device_id=self._next_id,
            hardware_id=hardware_id,
            display_name=None,
            status=DeviceStatus.PENDING,
            location=make_location(location_id, "Unknown"),
        )
        self._next_id += 1
        self.devices.append(device)
        return device

    async def update(self, device_id: int, data: dict) -> Device | None:
        self.updates.append((device_id, dict(data)))
        device = await self.get_by_id(device_id)
        if device:
            for key, value in data.items():
                setattr(device, key, value)
        return device


class FakeLocationRepository:
    def __init__(self, locations: Sequence[Location] = ()):
        self.locations: list[Location] = list(locations)
        self.created: list[str] = []
        self._next_id = max((loc.id for loc in self.locations), default=0) + 1

    async def get_by_display_name(self, display_name: str) -> Location | None:
        return next((loc for loc in self.locations if loc.display_name == display_name), None)

    async def create(self, name: str) -> Location:
        self.created.append(name)
        location = make_location(self._next_id, name)
        self._next_id += 1
        self.locations.append(location)
        return location

    async def get_or_create(self, name: str) -> Location:
        return await self.get_by_display_name(name) or await self.create(name)


class FakeTelemetryRepository:
    def __init__(
        self,
        readings: Sequence[ClimateReading] = (),
        series_rows: Sequence[Any] = (),
        current_rows: Sequence[Any] = (),
        count: int | None = None,
    ):
        self.readings = list(readings)
        self.series_rows = list(series_rows)
        self.current_rows = list(current_rows)
        self._count = count
        self.added: list[dict] = []
        self.filter_calls: list[dict] = []
        self.count_calls: list[dict] = []
        self.series_calls: list[dict] = []
        self.current_calls: list[Any] = []

    async def add_telemetry(self, device_id, climate_data, location_name, ts=None):
        record = {
            "device_id": device_id,
            "climate_data": climate_data,
            "location_name": location_name,
            "ts": ts,
        }
        self.added.append(record)
        return make_reading(
            device_id=device_id,
            location_snapshot=location_name,
            timestamp=ts or climate_data.timestamp,
        )

    async def get_latest_telemetry(self, device_id: int) -> Sequence[ClimateReading]:
        return [r for r in self.readings if r.device_id == device_id]

    async def get_by_filters(self, **kwargs) -> Sequence[ClimateReading]:
        self.filter_calls.append(kwargs)
        return list(self.readings)

    async def count_by_filters(self, **kwargs) -> int:
        self.count_calls.append(kwargs)
        return self._count if self._count is not None else len(self.readings)

    async def get_series(self, **kwargs) -> Sequence[Any]:
        self.series_calls.append(kwargs)
        return list(self.series_rows)

    async def get_current_readings(self, window) -> Sequence[Any]:
        self.current_calls.append(window)
        return list(self.current_rows)
