"""The factories exist because services are built from two entry points — HTTP
requests via deps.py and the MQTT hub, which makes its own sessions. Both must
end up with the same wiring over whichever session they were handed."""

from app.infrastructure.repositories import DeviceRepository, LocationRepository, TelemetryRepository
from app.infrastructure.service_factories import create_device_service, create_telemetry_service
from app.services.device_service import DeviceService
from app.services.telemetry_service import TelemetryService
from tests.fakes import FakeSession, as_session


def test_create_telemetry_service_wires_both_repositories_to_one_session():
    session = FakeSession()

    service = create_telemetry_service(as_session(session))

    assert isinstance(service, TelemetryService)
    assert isinstance(service.repo, TelemetryRepository)
    assert isinstance(service.device_repo, DeviceRepository)
    assert service.session is session
    assert service.repo.session is session
    assert service.device_repo.session is session


def test_create_device_service_wires_both_repositories_to_one_session():
    session = FakeSession()

    service = create_device_service(as_session(session))

    assert isinstance(service, DeviceService)
    assert isinstance(service.repo, DeviceRepository)
    assert isinstance(service.location_repo, LocationRepository)
    assert service.db_session is session
    assert service.repo.session is session
    assert service.location_repo.session is session


def test_each_call_builds_a_fresh_service():
    session = FakeSession()

    assert create_telemetry_service(as_session(session)) is not create_telemetry_service(as_session(session))
    assert create_device_service(as_session(session)) is not create_device_service(as_session(session))


async def test_deps_build_services_over_the_request_session():
    from app.core.deps import get_device_service, get_telemetry_service

    session = FakeSession()

    assert (await get_telemetry_service(as_session(session))).session is session
    assert (await get_device_service(as_session(session))).db_session is session
