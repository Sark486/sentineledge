from app.exceptions.sentinet_not_found_error import SentinelNotFoundError
from app.infrastructure.models import DeviceStatus
from tests.fakes import make_device, make_location, make_reading

BASE = "/api/v1/devices"


# --------------------------------------------------------------------------- #
# GET /devices/
# --------------------------------------------------------------------------- #


async def test_list_devices_returns_a_paginated_envelope(client, device_service):
    devices = [
        make_device(1, "pi-01", "Kitchen Pi", location=make_location(1, "Kitchen")),
        make_device(2, "pi-02", "Garage Pi", location=make_location(2, "Garage")),
    ]
    device_service.set_return("list_devices", devices).set_return("count_devices", 2)

    response = await client.get(f"{BASE}/")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["offset"] == 0
    assert [d["hardware_id"] for d in body["data"]] == ["pi-01", "pi-02"]


async def test_list_devices_reports_the_full_list_as_the_limit(client, device_service):
    """This route is unpaginated, so limit mirrors the total rather than lying about a page size."""
    device_service.set_return("list_devices", [make_device(1)]).set_return("count_devices", 1)

    body = (await client.get(f"{BASE}/")).json()

    assert body["limit"] == body["count"] == 1


async def test_list_devices_serialises_the_nested_location(client, device_service):
    device_service.set_return(
        "list_devices", [make_device(1, location=make_location(3, "Attic"))]
    ).set_return("count_devices", 1)

    body = (await client.get(f"{BASE}/")).json()

    assert body["data"][0]["location"] == {"display_name": "Attic"}


async def test_list_devices_tolerates_a_device_with_no_location(client, device_service):
    device_service.set_return("list_devices", [make_device(1, location=None)]).set_return(
        "count_devices", 1
    )

    body = (await client.get(f"{BASE}/")).json()

    assert body["data"][0]["location"] is None


async def test_list_devices_with_no_devices(client, device_service):
    device_service.set_return("list_devices", []).set_return("count_devices", 0)

    body = (await client.get(f"{BASE}/")).json()

    assert body == {"count": 0, "limit": 0, "offset": 0, "data": []}


# --------------------------------------------------------------------------- #
# GET /devices/{id}
# --------------------------------------------------------------------------- #


async def test_get_device_returns_the_device(client, device_service):
    device_service.set_return("get_device_by_id", make_device(5, "pi-05", "Study Pi"))

    response = await client.get(f"{BASE}/5")

    assert response.status_code == 200
    assert response.json()["id"] == 5
    assert response.json()["hardware_id"] == "pi-05"
    assert device_service.args_of("get_device_by_id") == (5,)


async def test_get_device_404s_when_missing(client, device_service):
    device_service.set_return("get_device_by_id", None)

    response = await client.get(f"{BASE}/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found"}


async def test_get_device_rejects_a_non_numeric_id(client, device_service):
    response = await client.get(f"{BASE}/not-a-number")

    assert response.status_code == 422
    assert not device_service.called("get_device_by_id")


async def test_device_status_is_serialised_as_its_string_value(client, device_service):
    device_service.set_return(
        "get_device_by_id", make_device(1, status=DeviceStatus.BLOCKED)
    )

    assert (await client.get(f"{BASE}/1")).json()["status"] == "blocked"


# --------------------------------------------------------------------------- #
# PATCH /devices/{id}
# --------------------------------------------------------------------------- #


async def test_patch_device_forwards_the_payload(client, device_service):
    device_service.set_return("update_device", make_device(1, display_name="Renamed"))

    response = await client.patch(
        f"{BASE}/1", json={"location_name": "Attic", "display_name": "Renamed"}
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Renamed"
    device_id, schema = device_service.args_of("update_device")
    assert device_id == 1
    assert schema.location_name == "Attic"
    assert schema.display_name == "Renamed"


async def test_patch_device_activates_a_pending_device(client, device_service):
    """The pending -> active transition is what unblocks telemetry persistence."""
    device_service.set_return("update_device", make_device(1, status=DeviceStatus.ACTIVE))

    response = await client.patch(
        f"{BASE}/1", json={"location_name": "Kitchen", "status": "active"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert device_service.args_of("update_device")[1].status == "active"


async def test_patch_device_leaves_unsent_fields_unset(client, device_service):
    device_service.set_return("update_device", make_device(1))

    await client.patch(f"{BASE}/1", json={"location_name": "Attic"})

    schema = device_service.args_of("update_device")[1]
    assert schema.model_dump(exclude_unset=True) == {"location_name": "Attic"}


async def test_patch_device_requires_a_location_name(client, device_service):
    response = await client.patch(f"{BASE}/1", json={"display_name": "Renamed"})

    assert response.status_code == 422
    assert not device_service.called("update_device")


async def test_patch_device_404s_when_the_service_returns_nothing(client, device_service):
    device_service.set_return("update_device", None)

    response = await client.patch(f"{BASE}/999", json={"location_name": "Attic"})

    assert response.status_code == 404


async def test_patch_device_404s_when_the_service_raises_not_found(client, device_service):
    device_service.set_error("update_device", SentinelNotFoundError())

    response = await client.patch(f"{BASE}/999", json={"location_name": "Attic"})

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# GET /devices/{id}/latest
# --------------------------------------------------------------------------- #


async def test_latest_for_a_device_returns_the_readings(client, telemetry_service):
    telemetry_service.set_return(
        "get_latest_telemetry_by_device", [make_reading(device_id=3, temperature=20.5)]
    )

    response = await client.get(f"{BASE}/3/latest")

    assert response.status_code == 200
    assert response.json()[0]["temperature"] == 20.5


async def test_latest_for_a_device_404s_when_there_are_no_readings(client, telemetry_service):
    telemetry_service.set_return("get_latest_telemetry_by_device", [])

    response = await client.get(f"{BASE}/3/latest")

    assert response.status_code == 404
