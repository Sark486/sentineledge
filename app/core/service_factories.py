"""Composition root: builds services with their repositories over one session.

Lives in `core` rather than `infrastructure` because it is the one place that is
allowed to know every layer. Services are built from two entry points — HTTP
requests (via `app.core.deps`) and the MQTT hub, which opens its own sessions
outside the request cycle — and both must wire them identically.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.repositories import (
    DeviceRepository,
    LocationRepository,
    TelemetryRepository,
)
from app.services.device_service import DeviceService
from app.services.telemetry_service import TelemetryService


def create_telemetry_service(session: AsyncSession) -> TelemetryService:
    return TelemetryService(TelemetryRepository(session), DeviceRepository(session))


def create_device_service(session: AsyncSession) -> DeviceService:
    return DeviceService(session, DeviceRepository(session), LocationRepository(session))
