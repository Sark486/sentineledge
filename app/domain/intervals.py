"""Interval resolution for the climate time-series endpoint.

Picks which of the three physical sources (raw readings, 5-minute
rollup, hourly rollup) should back a `/telemetry/series` request,
given the requested interval (if any) and what data retention
actually allows for the requested time range. Pure, DB-free logic —
see app.infrastructure.repositories.TelemetryRepository for the
queries that consume `ResolvedInterval.source`.
"""

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta

# Retention constants must match migrations/versions/98e6c996836c_*.py.
RETENTION_RAW = timedelta(days=7)
RETENTION_5M = timedelta(days=30)

# Matches the existing 10-minute onlineStatus window on the Devices page.
ONLINE_WINDOW = timedelta(minutes=10)


class Interval(str, enum.Enum):
    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    ONE_HOUR = "1h"

    @property
    def rank(self) -> int:
        """Granularity rank: lower is finer. Used to pick the coarser of two intervals."""
        return _INTERVAL_RANK[self]


_INTERVAL_RANK: dict[Interval, int] = {
    Interval.ONE_MIN: 0,
    Interval.FIVE_MIN: 1,
    Interval.ONE_HOUR: 2,
}

SOURCE_TABLE: dict[Interval, str] = {
    Interval.ONE_MIN: "climate_readings",
    Interval.FIVE_MIN: "climate_5m",
    Interval.ONE_HOUR: "climate_1h",
}


@dataclass(frozen=True)
class ResolvedInterval:
    interval: Interval
    source: str
    downgraded: bool
    requested: Interval | None


def default_for_duration(duration: timedelta) -> Interval:
    """Readability default when the caller didn't request a specific interval.

    Must be monotonic: a longer range never resolves to a finer interval.
    """
    if duration <= timedelta(hours=6):
        return Interval.ONE_MIN
    if duration <= timedelta(days=2):
        return Interval.FIVE_MIN
    return Interval.ONE_HOUR


def retention_floor(age: timedelta) -> Interval:
    """Coarsest interval whose data still exists for a point this old."""
    if age > RETENTION_5M:
        return Interval.ONE_HOUR
    if age > RETENTION_RAW:
        return Interval.FIVE_MIN
    return Interval.ONE_MIN


def resolve_interval(
    requested: Interval | None,
    start: datetime,
    end: datetime,
    now: datetime,
) -> ResolvedInterval:
    base = requested if requested is not None else default_for_duration(end - start)
    floor = retention_floor(now - start)
    effective = base if base.rank >= floor.rank else floor
    downgraded = requested is not None and effective.rank > requested.rank

    return ResolvedInterval(
        interval=effective,
        source=SOURCE_TABLE[effective],
        downgraded=downgraded,
        requested=requested,
    )
