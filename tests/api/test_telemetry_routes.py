from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.domain.intervals import Interval
from app.services.telemetry_service import SeriesResult
from tests.fakes import make_device, make_location, make_reading

BASE = "/api/v1/telemetry"
START = datetime(2026, 7, 1, tzinfo=timezone.utc)
END = datetime(2026, 7, 15, tzinfo=timezone.utc)


def series_result(rows=(), interval=Interval.FIVE_MIN, requested=None, downgraded=False):
    return SeriesResult(
        interval=interval,
        requested=requested,
        downgraded=downgraded,
        start=START,
        end=END,
        rows=list(rows),
    )


def series_row(
    timestamp: datetime = START,
    device_id: int = 1,
    temperature: float | None = 20.0,
    humidity: float | None = 40.0,
    pressure: float | None = 1000.0,
):
    """Stands in for the (bucket, device_id, avg…) Row the repository returns."""
    return SimpleNamespace(
        timestamp=timestamp,
        device_id=device_id,
        temperature=temperature,
        humidity=humidity,
        pressure=pressure,
    )


# --------------------------------------------------------------------------- #
# GET /telemetry/
# --------------------------------------------------------------------------- #


async def test_list_telemetry_returns_a_paginated_envelope(client, telemetry_service):
    readings = [make_reading(temperature=21.0), make_reading(temperature=22.0)]
    telemetry_service.set_return("get_telemetry", (120, readings))

    response = await client.get(f"{BASE}/")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 120
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert [r["temperature"] for r in body["data"]] == [21.0, 22.0]


async def test_list_telemetry_defaults_every_filter_to_none(client, telemetry_service):
    telemetry_service.set_return("get_telemetry", (0, []))

    await client.get(f"{BASE}/")

    assert telemetry_service.kwargs_of("get_telemetry") == {
        "device_id": None,
        "location": None,
        "start_date": None,
        "end_date": None,
        "limit": 100,
        "offset": 0,
    }


async def test_list_telemetry_forwards_every_query_parameter(client, telemetry_service):
    telemetry_service.set_return("get_telemetry", (0, []))

    await client.get(
        f"{BASE}/",
        params={
            "device_id": 4,
            "location": "Garage",
            "start_date": START.isoformat(),
            "end_date": END.isoformat(),
            "limit": 25,
            "offset": 75,
        },
    )

    assert telemetry_service.kwargs_of("get_telemetry") == {
        "device_id": 4,
        "location": "Garage",
        "start_date": START,
        "end_date": END,
        "limit": 25,
        "offset": 75,
    }


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 1001},
        {"limit": "many"},
        {"offset": -1},
        {"device_id": "abc"},
        {"start_date": "yesterday"},
    ],
)
async def test_list_telemetry_rejects_out_of_range_parameters(client, telemetry_service, params):
    response = await client.get(f"{BASE}/", params=params)

    assert response.status_code == 422
    assert not telemetry_service.called("get_telemetry")


@pytest.mark.parametrize("limit", [1, 1000])
async def test_list_telemetry_accepts_the_limit_boundaries(client, telemetry_service, limit):
    telemetry_service.set_return("get_telemetry", (0, []))

    response = await client.get(f"{BASE}/", params={"limit": limit})

    assert response.status_code == 200
    assert telemetry_service.kwargs_of("get_telemetry")["limit"] == limit


async def test_list_telemetry_includes_the_nested_device(client, telemetry_service):
    reading = make_reading()
    reading.device = make_device(1, "pi-01", location=make_location(1, "Kitchen"))
    telemetry_service.set_return("get_telemetry", (1, [reading]))

    body = (await client.get(f"{BASE}/")).json()

    assert body["data"][0]["device"]["hardware_id"] == "pi-01"


async def test_list_telemetry_preserves_the_location_snapshot(client, telemetry_service):
    """The snapshot, not the device's current location, is what the row reports."""
    reading = make_reading(location_snapshot="Old Kitchen")
    telemetry_service.set_return("get_telemetry", (1, [reading]))

    body = (await client.get(f"{BASE}/")).json()

    assert body["data"][0]["location_snapshot"] == "Old Kitchen"


# --------------------------------------------------------------------------- #
# GET /telemetry/series
# --------------------------------------------------------------------------- #


async def test_series_returns_the_resolved_interval_and_range(client, telemetry_service):
    telemetry_service.set_return("get_series", series_result([series_row()]))

    response = await client.get(f"{BASE}/series")

    assert response.status_code == 200
    body = response.json()
    assert body["interval"] == "5m"
    assert body["requested_interval"] is None
    assert body["downgraded"] is False
    assert datetime.fromisoformat(body["start"]) == START
    assert datetime.fromisoformat(body["end"]) == END
    assert len(body["data"]) == 1


async def test_series_reports_a_downgrade_with_the_requested_interval(client, telemetry_service):
    telemetry_service.set_return(
        "get_series",
        series_result(interval=Interval.ONE_HOUR, requested=Interval.ONE_MIN, downgraded=True),
    )

    body = (await client.get(f"{BASE}/series", params={"interval": "1m"})).json()

    assert body["interval"] == "1h"
    assert body["requested_interval"] == "1m"
    assert body["downgraded"] is True


async def test_series_maps_repository_rows_onto_series_points(client, telemetry_service):
    row = series_row(device_id=7, temperature=19.25, humidity=51.5, pressure=998.75)
    telemetry_service.set_return("get_series", series_result([row]))

    point = (await client.get(f"{BASE}/series")).json()["data"][0]

    assert datetime.fromisoformat(point.pop("timestamp")) == START
    assert point == {
        "device_id": 7,
        "temperature": 19.25,
        "humidity": 51.5,
        "pressure": 998.75,
    }


async def test_series_tolerates_empty_buckets(client, telemetry_service):
    telemetry_service.set_return("get_series", series_result([series_row(temperature=None)]))

    point = (await client.get(f"{BASE}/series")).json()["data"][0]

    assert point["temperature"] is None


async def test_series_forwards_every_query_parameter(client, telemetry_service):
    telemetry_service.set_return("get_series", series_result())

    await client.get(
        f"{BASE}/series",
        params={
            "interval": "1h",
            "device_id": 2,
            "location": "Garage",
            "start_date": START.isoformat(),
            "end_date": END.isoformat(),
        },
    )

    assert telemetry_service.kwargs_of("get_series") == {
        "interval": Interval.ONE_HOUR,
        "device_id": 2,
        "location": "Garage",
        "start": START,
        "end": END,
    }


async def test_series_leaves_the_range_to_the_service_when_unspecified(client, telemetry_service):
    telemetry_service.set_return("get_series", series_result())

    await client.get(f"{BASE}/series")

    kwargs = telemetry_service.kwargs_of("get_series")
    assert kwargs["start"] is None
    assert kwargs["end"] is None
    assert kwargs["interval"] is None


@pytest.mark.parametrize("interval", ["1m", "5m", "1h"])
async def test_series_accepts_every_supported_interval(client, telemetry_service, interval):
    telemetry_service.set_return("get_series", series_result())

    response = await client.get(f"{BASE}/series", params={"interval": interval})

    assert response.status_code == 200
    assert telemetry_service.kwargs_of("get_series")["interval"] == Interval(interval)


@pytest.mark.parametrize("interval", ["30s", "1d", "hourly", ""])
async def test_series_rejects_an_unsupported_interval(client, telemetry_service, interval):
    response = await client.get(f"{BASE}/series", params={"interval": interval})

    assert response.status_code == 422
    assert not telemetry_service.called("get_series")


# --------------------------------------------------------------------------- #
# GET /telemetry/latest
# --------------------------------------------------------------------------- #


async def test_latest_returns_one_row_per_online_device(client, telemetry_service):
    rows = [
        SimpleNamespace(
            device_id=1,
            display_name="Kitchen Pi",
            location="Kitchen",
            timestamp=END,
            temperature=21.0,
            humidity=44.0,
            pressure=1013.0,
        ),
        SimpleNamespace(
            device_id=2,
            display_name="Garage Pi",
            location="Garage",
            timestamp=END,
            temperature=15.0,
            humidity=60.0,
            pressure=1011.0,
        ),
    ]
    telemetry_service.set_return("get_current_readings", rows)

    body = (await client.get(f"{BASE}/latest")).json()

    assert [r["device_id"] for r in body] == [1, 2]
    assert body[0]["location"] == "Kitchen"
    assert body[0]["display_name"] == "Kitchen Pi"


async def test_latest_returns_an_empty_list_when_every_device_is_offline(
    client, telemetry_service
):
    telemetry_service.set_return("get_current_readings", [])

    response = await client.get(f"{BASE}/latest")

    assert response.status_code == 200
    assert response.json() == []


async def test_latest_tolerates_a_device_with_no_name_or_location(client, telemetry_service):
    telemetry_service.set_return(
        "get_current_readings",
        [
            SimpleNamespace(
                device_id=3,
                display_name=None,
                location=None,
                timestamp=END,
                temperature=21.0,
                humidity=44.0,
                pressure=1013.0,
            )
        ],
    )

    row = (await client.get(f"{BASE}/latest")).json()[0]

    assert row["display_name"] is None
    assert row["location"] is None


# --------------------------------------------------------------------------- #
# GET /telemetry/by-device/{id} and /by-location/{location}
# --------------------------------------------------------------------------- #


async def test_by_device_pins_the_device_id_from_the_path(client, telemetry_service):
    telemetry_service.set_return("get_telemetry", (0, []))

    response = await client.get(f"{BASE}/by-device/9")

    assert response.status_code == 200
    kwargs = telemetry_service.kwargs_of("get_telemetry")
    assert kwargs["device_id"] == 9
    assert "location" not in kwargs


async def test_by_device_still_honours_the_range_and_paging(client, telemetry_service):
    telemetry_service.set_return("get_telemetry", (0, []))

    await client.get(
        f"{BASE}/by-device/9",
        params={"start_date": START.isoformat(), "end_date": END.isoformat(), "limit": 10, "offset": 20},
    )

    kwargs = telemetry_service.kwargs_of("get_telemetry")
    assert (kwargs["start_date"], kwargs["end_date"]) == (START, END)
    assert (kwargs["limit"], kwargs["offset"]) == (10, 20)


async def test_by_device_rejects_a_non_numeric_id(client, telemetry_service):
    response = await client.get(f"{BASE}/by-device/abc")

    assert response.status_code == 422
    assert not telemetry_service.called("get_telemetry")


async def test_by_device_returns_an_empty_page_rather_than_404(client, telemetry_service):
    """An unknown device is indistinguishable from one with no readings here."""
    telemetry_service.set_return("get_telemetry", (0, []))

    response = await client.get(f"{BASE}/by-device/12345")

    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_by_location_pins_the_location_from_the_path(client, telemetry_service):
    telemetry_service.set_return("get_telemetry", (0, []))

    response = await client.get(f"{BASE}/by-location/Garage")

    assert response.status_code == 200
    assert telemetry_service.kwargs_of("get_telemetry")["location"] == "Garage"


async def test_by_location_url_decodes_the_path_segment(client, telemetry_service):
    telemetry_service.set_return("get_telemetry", (0, []))

    await client.get(f"{BASE}/by-location/Living%20Room")

    assert telemetry_service.kwargs_of("get_telemetry")["location"] == "Living Room"


async def test_by_location_can_be_narrowed_to_one_device(client, telemetry_service):
    telemetry_service.set_return("get_telemetry", (0, []))

    await client.get(f"{BASE}/by-location/Garage", params={"device_id": 4})

    kwargs = telemetry_service.kwargs_of("get_telemetry")
    assert kwargs["location"] == "Garage"
    assert kwargs["device_id"] == 4


async def test_series_route_is_not_shadowed_by_the_by_device_route(client, telemetry_service):
    """`/series` is declared after `/` but before the path-parameter routes; a
    reordering that let `/by-device/{id}` swallow it would break the charts."""
    telemetry_service.set_return("get_series", series_result())

    response = await client.get(f"{BASE}/series")

    assert response.status_code == 200
    assert "interval" in response.json()
