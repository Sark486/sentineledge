"""Schema tests.

The read schemas are `from_attributes`, and they are fed three different shapes:
ORM instances (devices, readings) and plain SQLAlchemy `Row`s (series buckets,
current readings). These pin down that contract independently of the routers.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    ClimateReadingRead,
    CurrentReadingRead,
    DeviceRead,
    DeviceUpdate,
    PaginatedResponse,
    SeriesPoint,
    SeriesResponse,
)
from app.infrastructure.models import DeviceStatus
from tests.fakes import make_device, make_location, make_reading

TS = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# PaginatedResponse
# --------------------------------------------------------------------------- #


def test_paginated_response_carries_its_metadata():
    page = PaginatedResponse[SeriesPoint](
        count=250, limit=100, offset=100, data=[SeriesPoint(timestamp=TS, device_id=1)]
    )

    assert (page.count, page.limit, page.offset) == (250, 100, 100)
    assert len(page.data) == 1


def test_paginated_response_validates_its_item_type():
    with pytest.raises(ValidationError):
        PaginatedResponse[SeriesPoint].model_validate(
            {"count": 1, "limit": 1, "offset": 0, "data": [{"nope": True}]}
        )


def test_paginated_response_requires_every_metadata_field():
    with pytest.raises(ValidationError):
        PaginatedResponse[SeriesPoint].model_validate({"count": 1, "data": []})


# --------------------------------------------------------------------------- #
# Device schemas
# --------------------------------------------------------------------------- #


def test_device_read_from_an_orm_device():
    device = make_device(3, "pi-03", "Study Pi", location=make_location(2, "Study"))

    read = DeviceRead.model_validate(device)

    assert read.id == 3
    assert read.hardware_id == "pi-03"
    assert read.display_name == "Study Pi"
    assert read.location is not None
    assert read.location.display_name == "Study"


def test_device_read_serialises_the_status_enum_to_a_string():
    device = make_device(1, status=DeviceStatus.PENDING)

    assert DeviceRead.model_validate(device).status == "pending"


def test_device_read_allows_a_device_with_no_location_or_name():
    device = make_device(1, display_name=None, location=None)

    read = DeviceRead.model_validate(device)

    assert read.location is None
    assert read.display_name is None


def test_device_read_allows_a_never_seen_device():
    read = DeviceRead.model_validate(make_device(1, last_seen=None))

    assert read.last_seen is None


def test_device_update_accepts_any_subset_of_fields():
    """Every field is optional so a rename need not restate the location."""
    assert DeviceUpdate.model_validate({"display_name": "Renamed"}).location_name is None
    assert DeviceUpdate.model_validate({}).model_dump(exclude_unset=True) == {}


def test_device_update_tracks_which_fields_were_set():
    """`update_device` relies on exclude_unset so a partial PATCH cannot null a field."""
    schema = DeviceUpdate(location_name="Attic")

    assert schema.model_dump(exclude_unset=True) == {"location_name": "Attic"}
    assert schema.display_name is None
    assert schema.status is None


def test_device_update_carries_every_field_when_all_are_sent():
    schema = DeviceUpdate(
        location_name="Attic", display_name="Renamed", status=DeviceStatus.ACTIVE
    )

    assert schema.model_dump(exclude_unset=True) == {
        "location_name": "Attic",
        "display_name": "Renamed",
        "status": DeviceStatus.ACTIVE,
    }


def test_device_update_rejects_an_unknown_status():
    """Typed as the enum, so a bogus value is a 422 rather than a 500 from the
    enum column the repository would otherwise assign it to."""
    with pytest.raises(ValidationError):
        DeviceUpdate.model_validate({"status": "banana"})


# --------------------------------------------------------------------------- #
# Climate reading schemas
# --------------------------------------------------------------------------- #


def test_climate_reading_read_from_an_orm_reading():
    reading = make_reading(device_id=2, temperature=18.5, location_snapshot="Garage", timestamp=TS)

    read = ClimateReadingRead.model_validate(reading)

    assert read.device_id == 2
    assert read.temperature == 18.5
    assert read.location_snapshot == "Garage"
    assert read.timestamp == TS


def test_climate_reading_read_allows_null_measurements():
    """The columns are nullable, and continuous aggregates emit NULL for gaps."""
    reading = make_reading(temperature=None, humidity=None, pressure=None)

    read = ClimateReadingRead.model_validate(reading)

    assert (read.temperature, read.humidity, read.pressure) == (None, None, None)


def test_climate_reading_read_requires_a_location_snapshot():
    with pytest.raises(ValidationError):
        ClimateReadingRead.model_validate({"timestamp": TS, "device_id": 1})


def test_climate_reading_read_nests_the_device_when_present():
    reading = make_reading()
    reading.device = make_device(1, "pi-01")

    read = ClimateReadingRead.model_validate(reading)

    assert read.device is not None
    assert read.device.hardware_id == "pi-01"


# --------------------------------------------------------------------------- #
# Series schemas
# --------------------------------------------------------------------------- #


def test_series_point_from_a_row_like_object():
    row = SimpleNamespace(
        timestamp=TS, device_id=1, temperature=20.0, humidity=40.0, pressure=1000.0
    )

    point = SeriesPoint.model_validate(row)

    assert point.timestamp == TS
    assert point.device_id == 1
    assert point.temperature == 20.0


def test_series_point_allows_null_measurements():
    row = SimpleNamespace(
        timestamp=TS, device_id=1, temperature=None, humidity=None, pressure=None
    )

    assert SeriesPoint.model_validate(row).temperature is None


def test_series_point_requires_a_timestamp_and_device_id():
    with pytest.raises(ValidationError):
        SeriesPoint.model_validate(SimpleNamespace(temperature=20.0))


def test_series_response_renders_the_interval_metadata():
    response = SeriesResponse(
        interval="5m",
        requested_interval="1m",
        downgraded=True,
        start=TS,
        end=TS,
        data=[SeriesPoint(timestamp=TS, device_id=1)],
    )
    dumped = response.model_dump()

    assert dumped["interval"] == "5m"
    assert dumped["requested_interval"] == "1m"
    assert dumped["downgraded"] is True


def test_series_response_requested_interval_is_optional():
    response = SeriesResponse(interval="5m", downgraded=False, start=TS, end=TS, data=[])

    assert response.requested_interval is None


# --------------------------------------------------------------------------- #
# Current reading schema
# --------------------------------------------------------------------------- #


def test_current_reading_read_from_a_joined_row():
    row = SimpleNamespace(
        device_id=1,
        display_name="Kitchen Pi",
        location="Kitchen",
        timestamp=TS,
        temperature=21.0,
        humidity=44.0,
        pressure=1013.0,
    )

    read = CurrentReadingRead.model_validate(row)

    assert read.device_id == 1
    assert read.display_name == "Kitchen Pi"
    assert read.location == "Kitchen"


def test_current_reading_read_allows_an_unlocated_unnamed_device():
    """The location join is an outer join, so both fields can come back NULL."""
    row = SimpleNamespace(
        device_id=1,
        display_name=None,
        location=None,
        timestamp=TS,
        temperature=21.0,
        humidity=44.0,
        pressure=1013.0,
    )

    read = CurrentReadingRead.model_validate(row)

    assert read.display_name is None
    assert read.location is None
