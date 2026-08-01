"""Global test configuration.

Settings are read at import time by `app.core.config`, and `app.infrastructure.db`
builds an engine from them as a side effect of import. Pinning the values here —
before any `app.*` module is imported — keeps the suite independent of whatever
`.env` the developer happens to have. Nothing in the suite opens a connection.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["MQTT_HOST"] = "test-broker"

import pytest  # noqa: E402

from app.domain.events import DeviceEvents  # noqa: E402
from app.services.telemetry_service import TelemetryService  # noqa: E402


@pytest.fixture(autouse=True)
def reset_global_state():
    """`TelemetryService._location_cache` and the `DeviceEvents` listener list are
    class-level, so they leak across tests unless reset."""
    TelemetryService._location_cache.clear()
    DeviceEvents._on_update_listeners.clear()
    yield
    TelemetryService._location_cache.clear()
    DeviceEvents._on_update_listeners.clear()
