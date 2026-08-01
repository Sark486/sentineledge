from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.domain.events import DeviceEvents
from app.domain.intervals import ONLINE_WINDOW, Interval
from app.infrastructure.repositories import DeviceRepository, TelemetryRepository
from app.services.telemetry_service import TelemetryService
from tests.fakes import (
    FakeDeviceRepository,
    FakeSession,
    FakeTelemetryRepository,
    as_session,
    make_climate_data,
    make_device,
    make_location,
    make_reading,
    stands_in_for,
)

TS = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def build_service(devices=(), telemetry_repo=None):
    session = FakeSession()
    telemetry_repo = telemetry_repo or FakeTelemetryRepository()
    device_repo = FakeDeviceRepository(devices)
    return make_service(session, telemetry_repo, device_repo), telemetry_repo, device_repo


def make_service(session, telemetry_repo, device_repo) -> TelemetryService:
    return TelemetryService(
        as_session(session),
        stands_in_for(TelemetryRepository, telemetry_repo),
        stands_in_for(DeviceRepository, device_repo),
    )


# --------------------------------------------------------------------------- #
# save_telemetry
# --------------------------------------------------------------------------- #


async def test_save_telemetry_persists_with_the_devices_location_snapshot():
    device = make_device(1, location=make_location(1, "Kitchen"))
    service, telemetry_repo, _ = build_service([device])

    await service.save_telemetry(1, make_climate_data(temperature=22.0))

    assert len(telemetry_repo.added) == 1
    record = telemetry_repo.added[0]
    assert record["device_id"] == 1
    assert record["location_name"] == "Kitchen"
    assert record["climate_data"].temperature == 22.0


async def test_save_telemetry_drops_readings_for_an_unknown_device():
    service, telemetry_repo, _ = build_service()

    await service.save_telemetry(99, make_climate_data())

    assert telemetry_repo.added == []


async def test_save_telemetry_falls_back_to_unassigned_when_the_device_has_no_location():
    service, telemetry_repo, _ = build_service([make_device(1, location=None)])

    await service.save_telemetry(1, make_climate_data())

    assert telemetry_repo.added[0]["location_name"] == "Unassigned"


async def test_save_telemetry_defaults_the_timestamp_to_the_payloads_own():
    service, telemetry_repo, _ = build_service([make_device(1)])

    await service.save_telemetry(1, make_climate_data(timestamp=TS))

    assert telemetry_repo.added[0]["ts"] == TS


async def test_save_telemetry_prefers_an_explicit_timestamp():
    service, telemetry_repo, _ = build_service([make_device(1)])
    override = TS - timedelta(hours=3)

    await service.save_telemetry(1, make_climate_data(timestamp=TS), ts=override)

    assert telemetry_repo.added[0]["ts"] == override


# --------------------------------------------------------------------------- #
# Location cache
# --------------------------------------------------------------------------- #


async def test_location_name_is_cached_after_the_first_lookup():
    device = make_device(1, location=make_location(1, "Kitchen"))
    service, _, device_repo = build_service([device])

    await service.save_telemetry(1, make_climate_data())
    first_round = len(device_repo.get_by_id_calls)
    await service.save_telemetry(1, make_climate_data())

    # save_telemetry always re-checks the device exists; only the *location*
    # lookup is cached, so the second call must be one query cheaper.
    assert len(device_repo.get_by_id_calls) == first_round + 1


async def test_cached_location_survives_a_device_moving_until_invalidated():
    device = make_device(1, location=make_location(1, "Kitchen"))
    service, telemetry_repo, _ = build_service([device])

    await service.save_telemetry(1, make_climate_data())
    device.location = make_location(2, "Garage")
    await service.save_telemetry(1, make_climate_data())

    assert [r["location_name"] for r in telemetry_repo.added] == ["Kitchen", "Kitchen"]


async def test_invalidating_the_cache_picks_up_the_new_location():
    device = make_device(1, location=make_location(1, "Kitchen"))
    service, telemetry_repo, _ = build_service([device])

    await service.save_telemetry(1, make_climate_data())
    device.location = make_location(2, "Garage")
    TelemetryService.invalidate_location_cache(1)
    await service.save_telemetry(1, make_climate_data())

    assert [r["location_name"] for r in telemetry_repo.added] == ["Kitchen", "Garage"]


async def test_invalidating_an_uncached_device_is_harmless():
    TelemetryService.invalidate_location_cache(1234)

    assert TelemetryService._location_cache == {}


async def test_invalidation_only_evicts_the_named_device():
    devices = [
        make_device(1, "pi-01", location=make_location(1, "Kitchen")),
        make_device(2, "pi-02", location=make_location(2, "Garage")),
    ]
    service, _, _ = build_service(devices)

    await service.save_telemetry(1, make_climate_data())
    await service.save_telemetry(2, make_climate_data())
    TelemetryService.invalidate_location_cache(1)

    assert TelemetryService._location_cache == {2: "Garage"}


async def test_the_cache_is_shared_between_service_instances():
    """The MQTT hub builds a fresh service per message; the cache is class-level
    precisely so those instances do not each re-query the location."""
    device = make_device(1, location=make_location(1, "Kitchen"))
    device_repo = FakeDeviceRepository([device])
    first = make_service(FakeSession(), FakeTelemetryRepository(), device_repo)
    second = make_service(FakeSession(), FakeTelemetryRepository(), device_repo)

    await first.save_telemetry(1, make_climate_data())
    calls_after_first = len(device_repo.get_by_id_calls)
    await second.save_telemetry(1, make_climate_data())

    assert len(device_repo.get_by_id_calls) == calls_after_first + 1


def test_constructing_the_service_subscribes_to_device_updates():
    make_service(FakeSession(), FakeTelemetryRepository(), FakeDeviceRepository())

    assert TelemetryService.invalidate_location_cache in DeviceEvents._on_update_listeners


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Every TelemetryService instance appends another listener, and the MQTT hub "
        "builds one per message — the listener list grows without bound."
    ),
)
def test_repeated_construction_does_not_stack_duplicate_listeners():
    for _ in range(5):
        make_service(FakeSession(), FakeTelemetryRepository(), FakeDeviceRepository())

    assert len(DeviceEvents._on_update_listeners) == 1


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #


async def test_get_latest_telemetry_by_device_delegates_to_the_repository():
    reading = make_reading(device_id=1)
    service, _, _ = build_service(telemetry_repo=FakeTelemetryRepository(readings=[reading]))

    assert list(await service.get_latest_telemetry_by_device(1)) == [reading]


async def test_get_telemetry_returns_the_total_alongside_the_page():
    readings = [make_reading(), make_reading()]
    repo = FakeTelemetryRepository(readings=readings, count=57)
    service, _, _ = build_service(telemetry_repo=repo)

    count, rows = await service.get_telemetry(limit=2)

    assert count == 57
    assert list(rows) == readings


async def test_get_telemetry_forwards_every_filter_to_both_queries():
    repo = FakeTelemetryRepository()
    service, _, _ = build_service(telemetry_repo=repo)
    start, end = TS - timedelta(days=1), TS

    await service.get_telemetry(
        device_id=3, location="Garage", start_date=start, end_date=end, limit=25, offset=50
    )

    assert repo.count_calls == [
        {"device_id": 3, "location": "Garage", "start_date": start, "end_date": end}
    ]
    assert repo.filter_calls == [
        {
            "device_id": 3,
            "location": "Garage",
            "start_date": start,
            "end_date": end,
            "limit": 25,
            "offset": 50,
        }
    ]


async def test_get_telemetry_defaults_to_the_first_hundred_unfiltered():
    repo = FakeTelemetryRepository()
    service, _, _ = build_service(telemetry_repo=repo)

    await service.get_telemetry()

    assert repo.filter_calls[0]["limit"] == 100
    assert repo.filter_calls[0]["offset"] == 0
    assert repo.filter_calls[0]["device_id"] is None


async def test_get_current_readings_uses_the_shared_online_window():
    repo = FakeTelemetryRepository(current_rows=[SimpleNamespace(device_id=1)])
    service, _, _ = build_service(telemetry_repo=repo)

    rows = await service.get_current_readings()

    assert repo.current_calls == [ONLINE_WINDOW]
    assert len(list(rows)) == 1


# --------------------------------------------------------------------------- #
# get_series
# --------------------------------------------------------------------------- #


async def test_get_series_defaults_to_the_last_24_hours():
    repo = FakeTelemetryRepository()
    service, _, _ = build_service(telemetry_repo=repo)

    before = datetime.now(timezone.utc)
    result = await service.get_series()
    after = datetime.now(timezone.utc)

    assert before <= result.end <= after
    assert result.end - result.start == timedelta(hours=24)
    assert repo.series_calls[0]["start"] == result.start
    assert repo.series_calls[0]["end"] == result.end


async def test_get_series_backfills_the_start_from_an_explicit_end():
    repo = FakeTelemetryRepository()
    service, _, _ = build_service(telemetry_repo=repo)

    result = await service.get_series(end=TS)

    assert result.end == TS
    assert result.start == TS - timedelta(hours=24)


async def test_get_series_picks_the_source_from_the_resolved_interval():
    repo = FakeTelemetryRepository()
    service, _, _ = build_service(telemetry_repo=repo)
    now = datetime.now(timezone.utc)

    result = await service.get_series(start=now - timedelta(hours=1), end=now)

    assert result.interval == Interval.ONE_MIN
    assert repo.series_calls[0]["source"] == "climate_readings"
    assert result.downgraded is False
    assert result.requested is None


async def test_get_series_reports_a_retention_downgrade():
    repo = FakeTelemetryRepository()
    service, _, _ = build_service(telemetry_repo=repo)
    now = datetime.now(timezone.utc)

    result = await service.get_series(
        interval=Interval.ONE_MIN, start=now - timedelta(days=60), end=now
    )

    assert result.interval == Interval.ONE_HOUR
    assert result.requested == Interval.ONE_MIN
    assert result.downgraded is True
    assert repo.series_calls[0]["source"] == "climate_1h"


async def test_get_series_forwards_the_device_and_location_filters():
    repo = FakeTelemetryRepository()
    service, _, _ = build_service(telemetry_repo=repo)

    await service.get_series(device_id=2, location="Garage")

    assert repo.series_calls[0]["device_id"] == 2
    assert repo.series_calls[0]["location"] == "Garage"


async def test_get_series_returns_the_repository_rows_verbatim():
    rows = [SimpleNamespace(timestamp=TS, device_id=1, temperature=20.0)]
    repo = FakeTelemetryRepository(series_rows=rows)
    service, _, _ = build_service(telemetry_repo=repo)

    result = await service.get_series()

    assert list(result.rows) == rows
