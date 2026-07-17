from app.services.device_service import DeviceService
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.telemetry_service import TelemetryService
from app.infrastructure.repositories import TelemetryRepository, DeviceRepository, LocationRepository

def create_telemetry_service(session: AsyncSession) -> TelemetryService:
    telemetry_repo = TelemetryRepository(session)
    device_repo = DeviceRepository(session)
    return TelemetryService(session, telemetry_repo, device_repo)


def create_device_service(session: AsyncSession) -> DeviceService:
    device_repo = DeviceRepository(session)
    location_repo = LocationRepository(session)
    return DeviceService(session, device_repo, location_repo)
