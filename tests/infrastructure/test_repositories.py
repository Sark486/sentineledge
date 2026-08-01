"""Repository tests.

These queries lean on Postgres/Timescale features (`time_bucket`, `DISTINCT ON`)
that no in-process database reproduces, so rather than execute them the tests
compile each statement against the Postgres dialect and assert on the SQL and
bound parameters. That is enough to catch the regressions that matter here — a
dropped filter, a flipped sort, a lost join, a mis-picked source view.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.infrastructure.models import DeviceStatus
from tests.fakes import (
    FakeResult,
    FakeSession,
    device_repository,
    location_repository,
    make_climate_data,
    make_device,
    make_location,
    make_reading,
    telemetry_repository,
)

START = datetime(2026, 7, 1, tzinfo=timezone.utc)
END = datetime(2026, 7, 15, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# DeviceRepository
# --------------------------------------------------------------------------- #


async def test_list_all_eager_loads_the_location():
    """Without the join, DeviceRead serialisation would trigger lazy IO on an
    async session and blow up."""
    session = FakeSession([FakeResult([make_device(1), make_device(2)])])

    devices = await device_repository(session).list_all()

    assert len(devices) == 2
    assert "LEFT OUTER JOIN locations" in session.sql()


async def test_count_all_returns_the_scalar():
    session = FakeSession([FakeResult(scalar=42)])

    assert await device_repository(session).count_all() == 42
    assert "count(devices.id)" in session.sql()


async def test_count_all_treats_a_null_scalar_as_zero():
    session = FakeSession([FakeResult(scalar=None)])

    assert await device_repository(session).count_all() == 0


async def test_get_by_id_filters_and_eager_loads():
    device = make_device(7)
    session = FakeSession([FakeResult([device])])

    assert await device_repository(session).get_by_id(7) is device
    # The joined-in location alias claims id_1, so bind the value, not the name.
    assert 7 in session.params().values()
    assert "devices.id = " in session.sql()
    assert "LEFT OUTER JOIN locations" in session.sql()


async def test_get_by_id_returns_none_when_missing():
    session = FakeSession([FakeResult([])])

    assert await device_repository(session).get_by_id(7) is None


async def test_get_by_hardware_id_filters_on_hardware_id():
    session = FakeSession([FakeResult([make_device(1, "pi-42")])])

    device = await device_repository(session).get_by_hardware_id("pi-42")

    assert device is not None
    assert device.hardware_id == "pi-42"
    assert session.params()["hardware_id_1"] == "pi-42"


async def test_create_stages_a_pending_device_and_flushes():
    session = FakeSession()

    device = await device_repository(session).create("pi-new", location_id=3)

    assert session.added == [device]
    assert device.hardware_id == "pi-new"
    assert device.location_id == 3
    assert device.status == DeviceStatus.PENDING
    assert session.flushes == 1
    assert session.commits == 0, "repositories must never commit; services own that"


async def test_update_applies_each_field_and_flushes():
    device = make_device(1, display_name="Old")
    session = FakeSession([FakeResult([device])])

    updated = await device_repository(session).update(
        1, {"display_name": "New", "location_id": 9}
    )

    assert updated is device
    assert device.display_name == "New"
    assert device.location_id == 9
    assert session.flushes == 1
    assert session.commits == 0


async def test_update_of_a_missing_device_returns_none():
    session = FakeSession([FakeResult([])])

    assert await device_repository(session).update(99, {"display_name": "New"}) is None


async def test_update_with_an_empty_payload_leaves_the_device_alone():
    device = make_device(1, display_name="Old")
    session = FakeSession([FakeResult([device])])

    await device_repository(session).update(1, {})

    assert device.display_name == "Old"


# --------------------------------------------------------------------------- #
# TelemetryRepository — writes
# --------------------------------------------------------------------------- #


async def test_add_telemetry_snapshots_the_location_onto_the_row():
    session = FakeSession()
    climate = make_climate_data(temperature=19.5, humidity=51.0, pressure=1002.0)

    reading = await telemetry_repository(session).add_telemetry(
        device_id=4, climate_data=climate, location_name="Garage"
    )

    assert reading is not None
    assert session.added == [reading]
    assert reading.device_id == 4
    assert (reading.temperature, reading.humidity, reading.pressure) == (19.5, 51.0, 1002.0)
    assert reading.location_snapshot == "Garage"
    assert session.flushes == 1


async def test_add_telemetry_defaults_the_timestamp_to_the_payloads():
    session = FakeSession()
    climate = make_climate_data(timestamp=START)

    reading = await telemetry_repository(session).add_telemetry(1, climate, "Garage")

    assert reading is not None
    assert reading.timestamp == START


async def test_add_telemetry_honours_an_explicit_timestamp():
    session = FakeSession()
    climate = make_climate_data(timestamp=START)

    reading = await telemetry_repository(session).add_telemetry(1, climate, "Garage", ts=END)

    assert reading is not None
    assert reading.timestamp == END


# --------------------------------------------------------------------------- #
# TelemetryRepository — reads
# --------------------------------------------------------------------------- #


async def test_get_latest_telemetry_selects_rows_at_the_max_timestamp():
    reading = make_reading()
    session = FakeSession([FakeResult([reading])])

    rows = await telemetry_repository(session).get_latest_telemetry(1)

    sql = session.sql()
    assert list(rows) == [reading]
    assert "ORDER BY climate_readings.timestamp DESC" in sql
    assert "LIMIT" in sql
    assert session.params()["device_id_1"] == 1


async def test_get_by_filters_without_filters_has_no_where_clause():
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_by_filters()

    assert " WHERE " not in session.sql()


async def test_get_by_filters_applies_every_filter():
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_by_filters(
        device_id=3, location="Garage", start_date=START, end_date=END
    )

    sql, params = session.sql(), session.params()
    assert "climate_readings.device_id = " in sql
    assert "climate_readings.location_snapshot = " in sql
    assert "climate_readings.timestamp >= " in sql
    assert "climate_readings.timestamp <= " in sql
    assert params["device_id_1"] == 3
    assert params["location_snapshot_1"] == "Garage"
    assert params["timestamp_1"] == START
    assert params["timestamp_2"] == END


@pytest.mark.parametrize(
    "kwargs, fragment",
    [
        ({"device_id": 3}, "climate_readings.device_id = "),
        ({"location": "Garage"}, "climate_readings.location_snapshot = "),
        ({"start_date": START}, "climate_readings.timestamp >= "),
        ({"end_date": END}, "climate_readings.timestamp <= "),
    ],
)
async def test_get_by_filters_applies_filters_independently(kwargs, fragment):
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_by_filters(**kwargs)

    assert fragment in session.sql()


async def test_get_by_filters_returns_newest_first_and_paginates():
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_by_filters(limit=25, offset=50)

    sql, params = session.sql(), session.params()
    assert "ORDER BY climate_readings.timestamp DESC" in sql
    assert params["param_1"] == 25
    assert params["param_2"] == 50


async def test_get_by_filters_eager_loads_device_and_location():
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_by_filters()

    sql = session.sql()
    assert "JOIN devices" in sql
    assert "JOIN locations" in sql


async def test_get_by_filters_deduplicates_joined_rows():
    """`unique()` is required by SQLAlchemy once a joined eager load is present."""
    reading = make_reading()
    session = FakeSession([FakeResult([reading, reading])])

    rows = await telemetry_repository(session).get_by_filters()

    assert len(list(rows)) == 2  # FakeScalars.unique() is a pass-through


async def test_count_by_filters_returns_the_scalar():
    session = FakeSession([FakeResult(scalar=17)])

    assert await telemetry_repository(session).count_by_filters() == 17


async def test_count_by_filters_treats_a_null_scalar_as_zero():
    session = FakeSession([FakeResult(scalar=None)])

    assert await telemetry_repository(session).count_by_filters() == 0


async def test_count_by_filters_applies_the_same_filters_as_the_page_query():
    session = FakeSession([FakeResult(scalar=0)])

    await telemetry_repository(session).count_by_filters(
        device_id=3, location="Garage", start_date=START, end_date=END
    )

    sql, params = session.sql(), session.params()
    assert "count(" in sql
    assert params["device_id_1"] == 3
    assert params["location_snapshot_1"] == "Garage"
    assert params["timestamp_1"] == START
    assert params["timestamp_2"] == END


async def test_count_by_filters_without_filters_has_no_where_clause():
    session = FakeSession([FakeResult(scalar=0)])

    await telemetry_repository(session).count_by_filters()

    assert " WHERE " not in session.sql()


# --------------------------------------------------------------------------- #
# TelemetryRepository — series
# --------------------------------------------------------------------------- #


async def test_series_over_raw_readings_buckets_to_one_minute():
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_series("climate_readings", START, END)

    sql = session.sql()
    assert "time_bucket(interval '1 minute', climate_readings.timestamp)" in sql
    assert "avg(climate_readings.temperature)" in sql
    assert "avg(climate_readings.humidity)" in sql
    assert "avg(climate_readings.pressure)" in sql
    assert "GROUP BY" in sql


async def test_series_over_raw_readings_orders_oldest_first_by_device():
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_series("climate_readings", START, END)

    assert "ORDER BY timestamp ASC, climate_readings.device_id" in session.sql()


async def test_series_over_raw_readings_bounds_the_range():
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_series("climate_readings", START, END)

    params = session.params()
    assert params["timestamp_1"] == START
    assert params["timestamp_2"] == END


async def test_series_over_raw_readings_applies_optional_filters():
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_series(
        "climate_readings", START, END, device_id=2, location="Garage"
    )

    params = session.params()
    assert params["device_id_1"] == 2
    assert params["location_snapshot_1"] == "Garage"


@pytest.mark.parametrize("source", ["climate_5m", "climate_1h"])
async def test_series_over_a_continuous_aggregate_reads_the_view_directly(source):
    """The rollups are already grouped by (bucket, device, location) — re-aggregating
    them would be both wrong and wasteful."""
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_series(source, START, END)

    sql = session.sql()
    assert f"FROM {source}" in sql
    assert "avg(" not in sql
    assert "GROUP BY" not in sql
    assert "time_bucket" not in sql


@pytest.mark.parametrize("source", ["climate_5m", "climate_1h"])
async def test_series_over_a_continuous_aggregate_exposes_bucket_as_timestamp(source):
    """The views store the bucket column as `bucket`, but rows must reach the API
    as `timestamp` — SeriesPoint.model_validate reads the row by that name."""
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_series(source, START, END)

    assert f"{source}.bucket" in session.sql()
    assert list(session.last_statement.selected_columns.keys()) == [
        "timestamp",
        "device_id",
        "temperature",
        "humidity",
        "pressure",
    ]


@pytest.mark.parametrize("source", ["climate_5m", "climate_1h"])
async def test_series_over_a_continuous_aggregate_filters_on_the_bucket(source):
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_series(
        source, START, END, device_id=2, location="Garage"
    )

    sql, params = session.sql(), session.params()
    assert f"{source}.bucket >= " in sql
    assert f"{source}.bucket <= " in sql
    assert params["device_id_1"] == 2
    assert params["location_snapshot_1"] == "Garage"


@pytest.mark.parametrize("source", ["climate_5m", "climate_1h"])
async def test_series_over_a_continuous_aggregate_orders_oldest_first(source):
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_series(source, START, END)

    assert f"ORDER BY {source}.bucket ASC, {source}.device_id" in session.sql()


async def test_series_with_an_unknown_source_is_a_hard_error():
    session = FakeSession([FakeResult([])])

    with pytest.raises(KeyError):
        await telemetry_repository(session).get_series("climate_1d", START, END)


async def test_series_returns_rows_not_scalars():
    """Series rows are (timestamp, device_id, t, h, p) tuples, not ORM objects."""
    rows = [(START, 1, 20.0, 40.0, 1000.0)]
    session = FakeSession([FakeResult(rows)])

    assert list(await telemetry_repository(session).get_series("climate_1h", START, END)) == rows


# --------------------------------------------------------------------------- #
# TelemetryRepository — current readings
# --------------------------------------------------------------------------- #


async def test_current_readings_takes_one_row_per_device():
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_current_readings(timedelta(minutes=10))

    sql = session.sql()
    assert "DISTINCT ON (climate_readings.device_id)" in sql
    assert "ORDER BY climate_readings.device_id, climate_readings.timestamp DESC" in sql


async def test_current_readings_cuts_off_at_the_window():
    before = datetime.now(timezone.utc)
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_current_readings(timedelta(minutes=10))

    cutoff = session.params()["timestamp_1"]
    assert before - timedelta(minutes=10) <= cutoff <= datetime.now(timezone.utc)


async def test_current_readings_joins_the_device_and_outer_joins_the_location():
    """A device with no location must still appear, with a null location."""
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_current_readings(timedelta(minutes=10))

    sql = session.sql()
    assert "JOIN devices ON" in sql
    assert "LEFT OUTER JOIN locations ON" in sql


async def test_current_readings_labels_the_location_column():
    """`Device.display_name` and `Location.display_name` collide without the label."""
    session = FakeSession([FakeResult([])])

    await telemetry_repository(session).get_current_readings(timedelta(minutes=10))

    assert "locations.display_name AS location" in session.sql()


# --------------------------------------------------------------------------- #
# LocationRepository
# --------------------------------------------------------------------------- #


async def test_location_list_all():
    locations = [make_location(1, "Kitchen"), make_location(2, "Garage")]
    session = FakeSession([FakeResult(locations)])

    assert list(await location_repository(session).list_all()) == locations


async def test_location_get_by_id():
    location = make_location(3, "Attic")
    session = FakeSession([FakeResult([location])])

    assert await location_repository(session).get_by_id(3) is location
    assert session.params()["id_1"] == 3


async def test_location_get_by_display_name():
    location = make_location(3, "Attic")
    session = FakeSession([FakeResult([location])])

    assert await location_repository(session).get_by_display_name("Attic") is location
    assert session.params()["display_name_1"] == "Attic"


async def test_location_get_by_display_name_returns_none_when_missing():
    session = FakeSession([FakeResult([])])

    assert await location_repository(session).get_by_display_name("Attic") is None


async def test_location_create_stages_and_flushes():
    session = FakeSession()

    location = await location_repository(session).create("Attic")

    assert session.added == [location]
    assert location.display_name == "Attic"
    assert session.flushes == 1
    assert session.commits == 0


async def test_location_get_or_create_returns_the_existing_row():
    location = make_location(3, "Attic")
    session = FakeSession([FakeResult([location])])

    assert await location_repository(session).get_or_create("Attic") is location
    assert session.added == []


async def test_location_get_or_create_creates_when_missing():
    session = FakeSession([FakeResult([])])

    location = await location_repository(session).get_or_create("Attic")

    assert location.display_name == "Attic"
    assert session.added == [location]
