"""App-level wiring: health, routing prefixes, CORS, the not-found handler and
the lifespan that owns the MQTT hub task."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.exceptions.sentinet_not_found_error import SentinelNotFoundError
from app.main import app, lifespan, sentinel_not_found_handler


async def test_health_endpoint(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unknown_route_is_a_404(client):
    assert (await client.get("/nope")).status_code == 404


async def test_routers_are_mounted_under_the_versioned_prefix():
    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/api/v1/devices/" in paths
    assert "/api/v1/telemetry/" in paths
    assert "/api/v1/telemetry/series" in paths
    assert "/api/v1/telemetry/latest" in paths


async def test_the_versioned_prefix_comes_from_settings():
    assert Settings(
        database_url="x", redis_url="y", mqtt_host="z"
    ).API_V1_STR == "/api/v1"


async def test_not_found_handler_maps_the_domain_error_to_a_404():
    response = await sentinel_not_found_handler(None, SentinelNotFoundError())

    assert response.status_code == 404


async def test_not_found_handler_does_not_leak_the_exception_message():
    response = await sentinel_not_found_handler(None, SentinelNotFoundError("device 42 in shard 7"))

    assert b"shard" not in response.body
    assert b"Resource not found" in response.body


async def test_cors_allows_the_vite_dev_origin(client):
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_cors_does_not_echo_an_unlisted_origin(client):
    response = await client.get("/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers


async def test_lifespan_starts_the_mqtt_hub_and_cancels_it_on_shutdown(monkeypatch):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_start():
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr("app.main.mqtt_manager.start", fake_start)

    async with lifespan(app):
        await asyncio.wait_for(started.wait(), timeout=1)

    assert cancelled.is_set()


async def test_lifespan_swallows_a_hub_that_crashes_on_shutdown(monkeypatch):
    """`gather(..., return_exceptions=True)` means a broken hub must not turn
    shutdown into an error."""

    async def exploding_start():
        raise RuntimeError("broker vanished")

    monkeypatch.setattr("app.main.mqtt_manager.start", exploding_start)

    async with lifespan(app):
        pass


async def test_app_serves_requests_without_the_lifespan():
    """Sanity check for the fixture setup: no MQTT broker is needed to serve HTTP."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.get("/health")).status_code == 200


def test_openapi_schema_builds():
    """A response_model that cannot be rendered breaks /docs, which is easy to miss."""
    schema = app.openapi()

    assert "/api/v1/telemetry/series" in schema["paths"]
    assert "/api/v1/devices/{device_id}" in schema["paths"]


@pytest.mark.parametrize(
    "field, value",
    [("database_url", "postgresql+asyncpg://u:p@h/db"), ("redis_url", "redis://h:6379/0")],
)
def test_settings_read_their_required_fields(field, value):
    settings = Settings(**{field: value, **_other_fields(field)})

    assert getattr(settings, field) == value


def test_settings_ignore_unknown_keys():
    settings = Settings.model_validate(
        {"database_url": "x", "redis_url": "y", "mqtt_host": "z", "something_unrelated": "!"}
    )

    assert not hasattr(settings, "something_unrelated")


def _other_fields(exclude: str) -> dict:
    defaults = {"database_url": "x", "redis_url": "y", "mqtt_host": "z"}
    defaults.pop(exclude)
    return defaults
