from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.sensors import EnvironmentalData


def test_timestamp_defaults_to_an_aware_utc_now():
    before = datetime.now(UTC)
    data = EnvironmentalData(temperature=21.0, humidity=40.0, pressure=1000.0, source="pi-01")
    after = datetime.now(UTC)

    assert data.timestamp.tzinfo is not None
    assert before <= data.timestamp <= after


def test_explicit_timestamp_is_preserved():
    ts = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    data = EnvironmentalData(
        temperature=21.0, humidity=40.0, pressure=1000.0, source="pi-01", timestamp=ts
    )

    assert data.timestamp == ts


def test_iso_timestamp_string_is_parsed():
    data = EnvironmentalData.model_validate(
        {
            "temperature": 21.0,
            "humidity": 40.0,
            "pressure": 1000.0,
            "source": "pi-01",
            "timestamp": "2026-07-15T12:00:00+00:00",
        }
    )

    assert data.timestamp == datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def test_numeric_strings_are_coerced_to_floats():
    """MQTT payloads are JSON, so a publisher sending "21.5" must still validate."""
    data = EnvironmentalData.model_validate(
        {"temperature": "21.5", "humidity": "40", "pressure": "1000.1", "source": "pi-01"}
    )

    assert (data.temperature, data.humidity, data.pressure) == (21.5, 40.0, 1000.1)


@pytest.mark.parametrize("missing", ["temperature", "humidity", "pressure", "source"])
def test_every_field_but_timestamp_is_required(missing):
    payload = {
        "temperature": 21.0,
        "humidity": 40.0,
        "pressure": 1000.0,
        "source": "pi-01",
    }
    payload.pop(missing)

    with pytest.raises(ValidationError):
        EnvironmentalData.model_validate(payload)


def test_non_numeric_reading_is_rejected():
    with pytest.raises(ValidationError):
        EnvironmentalData.model_validate(
            {"temperature": "warm", "humidity": 40.0, "pressure": 1000.0, "source": "pi-01"}
        )
