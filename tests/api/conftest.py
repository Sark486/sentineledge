"""HTTP-level fixtures.

The routers are exercised through the real FastAPI app with the two service
dependencies overridden, which keeps query-parameter validation, response-model
serialisation and the SentinelNotFoundError handler in the loop while leaving
the database out of it. `ASGITransport` does not run the lifespan, so the MQTT
hub never starts.
"""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.deps import get_device_service, get_telemetry_service
from app.main import app


class StubService:
    """Replays queued return values and records the keyword arguments it was
    called with, so a router test can assert on exactly what was forwarded.

    Any service method the router calls without a queued value is an error —
    that keeps a router quietly gaining a dependency from passing silently.
    """

    def __init__(self, **returns: Any):
        self._returns: dict[str, Any] = dict(returns)
        self._calls: dict[str, list[tuple[tuple, dict]]] = {}

    def set_return(self, name: str, value: Any) -> "StubService":
        self._returns[name] = value
        return self

    def set_error(self, name: str, exc: BaseException) -> "StubService":
        self._returns[name] = exc
        return self

    def kwargs_of(self, name: str, index: int = 0) -> dict:
        return self._calls[name][index][1]

    def args_of(self, name: str, index: int = 0) -> tuple:
        return self._calls[name][index][0]

    def call_count(self, name: str) -> int:
        return len(self._calls.get(name, []))

    def called(self, name: str) -> bool:
        return name in self._calls

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        async def call(*args: Any, **kwargs: Any) -> Any:
            self._calls.setdefault(name, []).append((args, kwargs))
            if name not in self._returns:
                raise AssertionError(f"router called unstubbed service method {name!r}")
            value = self._returns[name]
            if isinstance(value, BaseException):
                raise value
            return value

        return call


@pytest.fixture
def device_service() -> StubService:
    return StubService()


@pytest.fixture
def telemetry_service() -> StubService:
    return StubService()


@pytest.fixture
async def client(device_service, telemetry_service):
    app.dependency_overrides[get_device_service] = lambda: device_service
    app.dependency_overrides[get_telemetry_service] = lambda: telemetry_service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
