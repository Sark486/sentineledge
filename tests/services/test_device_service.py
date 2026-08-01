from datetime import UTC, datetime, timedelta

from app.api.schemas import DeviceUpdate
from app.domain.devices import DEFAULT_LOCATION_NAME, LIVENESS_REFRESH
from app.infrastructure.models import DeviceStatus
from app.infrastructure.repositories import DeviceRepository, LocationRepository
from app.services.device_service import DeviceService
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


async def test_create_device_delegates_to_the_repository():
    service, session, device_repo, _ = build_service()

    device = await service.create_device("pi-new", location_id=5)

    assert device_repo.created == [("pi-new", 5)]
    assert device.hardware_id == "pi-new"
    # The MQTT hub owns the transaction for the whole message.
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
    assert session.commits == 0


async def test_get_or_create_creates_the_unknown_location_once():
    service, _, _, location_repo = build_service()

    await service.get_or_create_device("pi-a")
    await service.get_or_create_device("pi-b")

    assert location_repo.created == [DEFAULT_LOCATION_NAME]


async def test_get_or_create_reuses_an_existing_default_location():
    unknown = make_location(9, DEFAULT_LOCATION_NAME)
    service, _, device_repo, location_repo = build_service(locations=[unknown])

    await service.get_or_create_device("pi-a")

    assert location_repo.created == []
    assert device_repo.created == [("pi-a", 9)]


async def test_get_or_create_does_no_location_work_for_a_known_device():
    """Only registration needs a location; the steady-state path is one lookup."""
    service, _, _, location_repo = build_service([make_device(1, "pi-01")])

    await service.get_or_create_device("pi-01")

    assert location_repo.created == []


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
        1,
        DeviceUpdate(location_name="Attic", display_name="New Name", status=DeviceStatus.ACTIVE),
    )

    assert device_repo.updates[0][1] == {
        "display_name": "New Name",
        "status": DeviceStatus.ACTIVE,
        "location_id": 1,
    }
    assert updated is not None
    assert updated.display_name == "New Name"
    assert updated.status == DeviceStatus.ACTIVE


async def test_update_device_omits_fields_the_caller_never_set():
    """`exclude_unset` keeps a partial PATCH from nulling display_name/status."""
    device = make_device(1, display_name="Keep Me")
    service, _, device_repo, _ = build_service([device], locations=[make_location(1, "Attic")])

    await service.update_device(1, DeviceUpdate(location_name="Attic"))

    assert device_repo.updates[0][1] == {"location_id": 1}
    assert device.display_name == "Keep Me"


async def test_update_device_rereads_the_committed_row():
    """Re-read rather than session.refresh(): refresh reloads columns only and
    would drop the eagerly loaded location the response serialises."""
    attic = make_location(1, "Attic")
    device = make_device(1, location=attic)
    service, session, device_repo, _ = build_service([device], locations=[attic])

    updated = await service.update_device(1, DeviceUpdate(location_name="Attic"))

    assert session.commits == 1
    assert session.refreshed == []
    assert device_repo.get_by_id_calls[-1] == 1
    assert updated is not None
    assert updated.location is not None


async def test_update_device_returns_none_for_an_unknown_device():
    service, session, _, _ = build_service([make_device(1)])

    assert await service.update_device(99, DeviceUpdate(location_name="Attic")) is None
    assert session.commits == 0
    assert session.refreshed == []


async def test_update_device_can_change_status_without_restating_the_location():
    device = make_device(1, status=DeviceStatus.PENDING)
    service, _, device_repo, location_repo = build_service([device])

    updated = await service.update_device(1, DeviceUpdate(status=DeviceStatus.ACTIVE))

    assert device_repo.updates == [(1, {"status": DeviceStatus.ACTIVE})]
    assert location_repo.created == []
    assert updated is not None
    assert updated.status == DeviceStatus.ACTIVE


# --------------------------------------------------------------------------- #
# mark_online
# --------------------------------------------------------------------------- #

STALE = LIVENESS_REFRESH + timedelta(seconds=1)
RECENT = LIVENESS_REFRESH - timedelta(seconds=1)


async def test_mark_online_is_a_noop_for_an_unknown_device():
    service, session, _, _ = build_service([make_device(1)])

    await service.mark_online(99)

    assert session.commits == 0


async def test_mark_online_writes_when_the_device_has_never_been_seen():
    device = make_device(1, last_seen=None)
    service, _, _, _ = build_service([device])

    await service.mark_online(1)

    assert device.last_seen is not None


async def test_mark_online_writes_once_the_throttle_window_has_elapsed():
    stale = datetime.now(UTC) - STALE
    device = make_device(1, last_seen=stale)
    service, _, _, _ = build_service([device])

    await service.mark_online(1)

    assert device.last_seen > stale


async def test_mark_online_is_throttled_inside_the_window():
    """Telemetry arrives far more often than the online window needs; only the
    first message past the refresh interval dirties the row."""
    recent = datetime.now(UTC) - RECENT
    device = make_device(1, last_seen=recent)
    service, _, _, _ = build_service([device])

    await service.mark_online(1)

    assert device.last_seen == recent


async def test_repeated_mark_online_calls_write_only_once():
    device = make_device(1, last_seen=None)
    service, _, _, _ = build_service([device])

    await service.mark_online(1)
    first_write = device.last_seen
    for _ in range(4):
        await service.mark_online(1)

    assert device.last_seen == first_write


async def test_the_refresh_interval_stays_inside_the_online_window():
    """A device refreshing on schedule must never read as offline."""
    from app.domain.intervals import ONLINE_WINDOW

    assert LIVENESS_REFRESH < ONLINE_WINDOW
