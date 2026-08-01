from datetime import datetime, timedelta, timezone

import pytest

from app.api.schemas import DeviceUpdate
from app.infrastructure.models import DeviceStatus
from app.services.device_service import DeviceService
from app.infrastructure.repositories import DeviceRepository, LocationRepository
from tests.fakes import (
    FakeDeviceRepository,
    FakeLocationRepository,
    FakeSession,
    as_session,
    make_device,
    make_location,
    stands_in_for,
)


def build_service(devices=(), locations=(), device_repo=None, session=None):
    session = session or FakeSession()
    device_repo = device_repo or FakeDeviceRepository(devices)
    location_repo = FakeLocationRepository(locations)
    service = DeviceService(
        as_session(session),
        stands_in_for(DeviceRepository, device_repo),
        stands_in_for(LocationRepository, location_repo),
    )
    return service, session, device_repo, location_repo


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #


async def test_list_devices_returns_every_device():
    devices = [make_device(1, "pi-01"), make_device(2, "pi-02")]
    service, _, _, _ = build_service(devices)

    assert list(await service.list_devices()) == devices


async def test_count_devices_returns_the_repository_total():
    service, _, _, _ = build_service([make_device(1), make_device(2), make_device(3)])

    assert await service.count_devices() == 3


async def test_get_device_by_id_returns_the_match():
    wanted = make_device(2, "pi-02")
    service, _, _, _ = build_service([make_device(1, "pi-01"), wanted])

    assert await service.get_device_by_id(2) is wanted


async def test_get_device_by_id_returns_none_when_absent():
    service, _, _, _ = build_service([make_device(1)])

    assert await service.get_device_by_id(99) is None


# --------------------------------------------------------------------------- #
# create_device / get_or_create_device
# --------------------------------------------------------------------------- #


async def test_create_device_commits():
    service, session, device_repo, _ = build_service()

    device = await service.create_device("pi-new", location_id=5)

    assert device_repo.created == [("pi-new", 5)]
    assert session.commits == 1
    assert device.hardware_id == "pi-new"


async def test_create_device_does_not_commit_when_the_repository_returns_nothing():
    device_repo = FakeDeviceRepository(create_returns=None)
    service, session, _, _ = build_service(device_repo=device_repo)

    assert await service.create_device("pi-new", location_id=5) is None
    assert session.commits == 0


async def test_get_or_create_returns_the_existing_device_untouched():
    existing = make_device(1, "pi-01")
    service, session, device_repo, location_repo = build_service([existing])

    assert await service.get_or_create_device("pi-01") is existing
    assert device_repo.created == []
    assert session.commits == 0


async def test_get_or_create_registers_an_unknown_device_as_pending():
    service, session, device_repo, _ = build_service()

    device = await service.get_or_create_device("pi-unseen")

    assert device.hardware_id == "pi-unseen"
    assert device.status == DeviceStatus.PENDING
    assert device_repo.created == [("pi-unseen", 1)]
    assert session.commits == 1


async def test_get_or_create_creates_the_unknown_location_once():
    service, _, _, location_repo = build_service()

    await service.get_or_create_device("pi-a")
    await service.get_or_create_device("pi-b")

    assert location_repo.created == ["Unknown"]


async def test_get_or_create_reuses_an_existing_unknown_location():
    unknown = make_location(9, "Unknown")
    service, _, device_repo, location_repo = build_service(locations=[unknown])

    await service.get_or_create_device("pi-a")

    assert location_repo.created == []
    assert device_repo.created == [("pi-a", 9)]


async def test_get_or_create_still_resolves_the_location_for_a_known_device():
    """The location lookup runs before the device check, so it is created either way."""
    service, _, _, location_repo = build_service([make_device(1, "pi-01")])

    await service.get_or_create_device("pi-01")

    assert location_repo.created == ["Unknown"]


# --------------------------------------------------------------------------- #
# update_device
# --------------------------------------------------------------------------- #


async def test_update_device_translates_location_name_to_a_location_id():
    device = make_device(1, "pi-01")
    living_room = make_location(4, "Living Room")
    service, session, device_repo, location_repo = build_service(
        [device], locations=[living_room]
    )

    updated = await service.update_device(1, DeviceUpdate(location_name="Living Room"))

    assert device_repo.updates == [(1, {"location_id": 4})]
    assert "location_name" not in device_repo.updates[0][1]
    assert updated is not None
    assert updated.location_id == 4
    assert location_repo.created == []
    assert session.commits == 1


async def test_update_device_creates_a_missing_location():
    service, _, device_repo, location_repo = build_service([make_device(1)])

    await service.update_device(1, DeviceUpdate(location_name="Attic"))

    assert location_repo.created == ["Attic"]
    assert device_repo.updates[0][1]["location_id"] == location_repo.locations[-1].id


async def test_update_device_passes_through_other_fields():
    device = make_device(1, display_name="Old Name", status=DeviceStatus.PENDING)
    service, _, device_repo, _ = build_service([device], locations=[make_location(1, "Attic")])

    updated = await service.update_device(
        1, DeviceUpdate(location_name="Attic", display_name="New Name", status="active")
    )

    assert device_repo.updates[0][1] == {
        "display_name": "New Name",
        "status": "active",
        "location_id": 1,
    }
    assert updated is not None
    assert updated.display_name == "New Name"
    assert updated.status == "active"


async def test_update_device_omits_fields_the_caller_never_set():
    """`exclude_unset` keeps a partial PATCH from nulling display_name/status."""
    device = make_device(1, display_name="Keep Me")
    service, _, device_repo, _ = build_service([device], locations=[make_location(1, "Attic")])

    await service.update_device(1, DeviceUpdate(location_name="Attic"))

    assert device_repo.updates[0][1] == {"location_id": 1}
    assert device.display_name == "Keep Me"


async def test_update_device_refreshes_the_committed_row():
    device = make_device(1)
    service, session, _, _ = build_service([device], locations=[make_location(1, "Attic")])

    await service.update_device(1, DeviceUpdate(location_name="Attic"))

    assert session.refreshed == [device]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "update_device refreshes unconditionally, so a PATCH against an unknown "
        "device blows up inside session.refresh(None) instead of returning None "
        "for the router to turn into a 404."
    ),
)
async def test_update_device_returns_none_for_an_unknown_device():
    service, session, _, _ = build_service([make_device(1)])

    assert await service.update_device(99, DeviceUpdate(location_name="Attic")) is None
    assert session.refreshed == []


# --------------------------------------------------------------------------- #
# mark_online
# --------------------------------------------------------------------------- #


async def test_mark_online_is_a_noop_for_an_unknown_device():
    service, session, _, _ = build_service([make_device(1)])

    await service.mark_online(99)

    assert session.commits == 0


async def test_mark_online_writes_when_the_device_has_never_been_seen():
    device = make_device(1, last_seen=None, is_online=False)
    service, session, _, _ = build_service([device])

    await service.mark_online(1)

    assert device.is_online is True
    assert device.last_seen is not None
    assert session.commits == 1


async def test_mark_online_writes_once_the_throttle_window_has_elapsed():
    stale = datetime.now(timezone.utc) - timedelta(seconds=301)
    device = make_device(1, last_seen=stale, is_online=False)
    service, session, _, _ = build_service([device])

    await service.mark_online(1)

    assert device.is_online is True
    assert device.last_seen > stale
    assert session.commits == 1


async def test_mark_online_is_throttled_inside_the_window():
    """Telemetry arrives far more often than every 300s; only the first write commits."""
    recent = datetime.now(timezone.utc) - timedelta(seconds=299)
    device = make_device(1, last_seen=recent, is_online=False)
    service, session, _, _ = build_service([device])

    await service.mark_online(1)

    assert device.last_seen == recent
    assert device.is_online is False
    assert session.commits == 0


async def test_repeated_mark_online_calls_commit_only_once():
    device = make_device(1, last_seen=None)
    service, session, _, _ = build_service([device])

    for _ in range(5):
        await service.mark_online(1)

    assert session.commits == 1
