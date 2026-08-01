from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.intervals import (
    SOURCE_TABLE,
    Interval,
    default_for_duration,
    resolve_interval,
    retention_floor,
)

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def test_last_few_hours_defaults_to_one_minute():
    start = NOW - timedelta(hours=4)
    resolved = resolve_interval(None, start, NOW, NOW)

    assert resolved.interval == Interval.ONE_MIN
    assert resolved.source == "climate_readings"
    assert resolved.downgraded is False
    assert resolved.requested is None


def test_yesterday_defaults_to_five_minute():
    start = NOW - timedelta(days=1)
    resolved = resolve_interval(None, start, NOW, NOW)

    assert resolved.interval == Interval.FIVE_MIN
    assert resolved.source == "climate_5m"
    assert resolved.downgraded is False
    assert resolved.requested is None


def test_two_years_defaults_to_one_hour():
    start = NOW - timedelta(days=730)
    resolved = resolve_interval(None, start, NOW, NOW)

    assert resolved.interval == Interval.ONE_HOUR
    assert resolved.source == "climate_1h"
    assert resolved.downgraded is False


def test_three_weeks_with_explicit_one_minute_downgrades_to_five_minute():
    start = NOW - timedelta(weeks=3)
    resolved = resolve_interval(Interval.ONE_MIN, start, NOW, NOW)

    assert resolved.interval == Interval.FIVE_MIN
    assert resolved.source == "climate_5m"
    assert resolved.downgraded is True
    assert resolved.requested == Interval.ONE_MIN


def test_short_but_old_window_auto_selects_five_minute_without_downgrade_flag():
    # A 2-day window that ended 3 weeks ago: short enough for 1m by
    # duration alone, but old enough that raw data has been retired.
    end = NOW - timedelta(weeks=3)
    start = end - timedelta(days=2)
    resolved = resolve_interval(None, start, end, NOW)

    assert resolved.interval == Interval.FIVE_MIN
    assert resolved.source == "climate_5m"
    assert resolved.downgraded is False


def test_boundary_exactly_seven_days_old_stays_at_raw():
    # Explicit 1m isolates the retention floor from the duration-based default.
    start = NOW - timedelta(days=7)
    resolved = resolve_interval(Interval.ONE_MIN, start, NOW, NOW)

    assert resolved.interval == Interval.ONE_MIN
    assert resolved.downgraded is False


def test_boundary_just_past_seven_days_old_drops_to_five_minute():
    start = NOW - timedelta(days=7, seconds=1)
    resolved = resolve_interval(Interval.ONE_MIN, start, NOW, NOW)

    assert resolved.interval == Interval.FIVE_MIN
    assert resolved.downgraded is True


def test_boundary_exactly_thirty_days_old_stays_at_five_minute():
    start = NOW - timedelta(days=30)
    resolved = resolve_interval(Interval.FIVE_MIN, start, NOW, NOW)

    assert resolved.interval == Interval.FIVE_MIN
    assert resolved.downgraded is False


def test_boundary_just_past_thirty_days_old_drops_to_one_hour():
    start = NOW - timedelta(days=30, seconds=1)
    resolved = resolve_interval(Interval.FIVE_MIN, start, NOW, NOW)

    assert resolved.interval == Interval.ONE_HOUR
    assert resolved.downgraded is True


@pytest.mark.parametrize(
    "duration, expected",
    [
        (timedelta(hours=1), Interval.ONE_MIN),
        (timedelta(hours=6), Interval.ONE_MIN),
        (timedelta(hours=6, seconds=1), Interval.FIVE_MIN),
        (timedelta(days=2), Interval.FIVE_MIN),
        (timedelta(days=2, seconds=1), Interval.ONE_HOUR),
        (timedelta(days=30), Interval.ONE_HOUR),
    ],
)
def test_default_for_duration_thresholds(duration, expected):
    start = NOW - duration
    resolved = resolve_interval(None, start, NOW, NOW)

    assert resolved.interval == expected


@pytest.mark.parametrize(
    "duration, expected",
    [
        (timedelta(0), Interval.ONE_MIN),
        (timedelta(hours=6), Interval.ONE_MIN),
        (timedelta(hours=6, seconds=1), Interval.FIVE_MIN),
        (timedelta(days=2), Interval.FIVE_MIN),
        (timedelta(days=2, seconds=1), Interval.ONE_HOUR),
        (timedelta(days=365), Interval.ONE_HOUR),
    ],
)
def test_default_for_duration_directly(duration, expected):
    assert default_for_duration(duration) == expected


def test_default_for_duration_is_monotonic():
    """A longer range must never resolve to a finer interval."""
    ranks = [
        default_for_duration(timedelta(minutes=step)).rank
        for step in range(0, 60 * 24 * 40, 137)
    ]

    assert ranks == sorted(ranks)


@pytest.mark.parametrize(
    "age, expected",
    [
        (timedelta(0), Interval.ONE_MIN),
        (timedelta(days=7), Interval.ONE_MIN),
        (timedelta(days=7, seconds=1), Interval.FIVE_MIN),
        (timedelta(days=30), Interval.FIVE_MIN),
        (timedelta(days=30, seconds=1), Interval.ONE_HOUR),
    ],
)
def test_retention_floor_thresholds(age, expected):
    assert retention_floor(age) == expected


def test_interval_ranks_are_ordered_coarsest_last():
    assert Interval.ONE_MIN.rank < Interval.FIVE_MIN.rank < Interval.ONE_HOUR.rank


def test_every_interval_maps_to_a_source_table():
    assert SOURCE_TABLE == {
        Interval.ONE_MIN: "climate_readings",
        Interval.FIVE_MIN: "climate_5m",
        Interval.ONE_HOUR: "climate_1h",
    }


@pytest.mark.parametrize("interval", list(Interval))
def test_resolved_source_always_matches_the_resolved_interval(interval):
    resolved = resolve_interval(interval, NOW - timedelta(hours=1), NOW, NOW)

    assert resolved.source == SOURCE_TABLE[resolved.interval]


def test_requested_interval_coarser_than_the_default_is_honored():
    """Asking for 1h over a 1h window is not a downgrade — the caller wanted it."""
    resolved = resolve_interval(Interval.ONE_HOUR, NOW - timedelta(hours=1), NOW, NOW)

    assert resolved.interval == Interval.ONE_HOUR
    assert resolved.downgraded is False
    assert resolved.requested == Interval.ONE_HOUR


def test_very_old_window_downgrades_all_the_way_to_one_hour():
    start = NOW - timedelta(days=400)
    resolved = resolve_interval(Interval.ONE_MIN, start, NOW, NOW)

    assert resolved.interval == Interval.ONE_HOUR
    assert resolved.source == "climate_1h"
    assert resolved.downgraded is True
    assert resolved.requested == Interval.ONE_MIN


def test_resolved_interval_is_immutable():
    resolved = resolve_interval(None, NOW - timedelta(hours=1), NOW, NOW)

    with pytest.raises(FrozenInstanceError):
        resolved.interval = Interval.ONE_HOUR  # type: ignore
