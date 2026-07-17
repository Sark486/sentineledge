from datetime import datetime, timedelta, timezone

import pytest

from app.domain.intervals import Interval, resolve_interval

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def test_yesterday_defaults_to_one_minute():
    start = NOW - timedelta(days=1)
    resolved = resolve_interval(None, start, NOW, NOW)

    assert resolved.interval == Interval.ONE_MIN
    assert resolved.source == "climate_readings"
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
        (timedelta(days=2), Interval.ONE_MIN),
        (timedelta(days=2, seconds=1), Interval.FIVE_MIN),
        (timedelta(days=30), Interval.FIVE_MIN),
        (timedelta(days=30, seconds=1), Interval.ONE_HOUR),
    ],
)
def test_default_for_duration_thresholds(duration, expected):
    start = NOW - duration
    resolved = resolve_interval(None, start, NOW, NOW)

    assert resolved.interval == expected
