"""Tests for the MQTT ingestion path.

`MQTTHub._handle_message` is the whole ingestion contract: topic parsing,
payload validation, device auto-registration, and the rule that only `active`
devices get their readings persisted. `start()` is a bare reconnect loop around
it and is covered separately with a stubbed client.
"""

import json

import aiomqtt
import pytest

from app.infrastructure.models import DeviceStatus
from app.infrastructure.repositories import (
    DeviceRepository,
    LocationRepository,
    TelemetryRepository,
)
from app.services import mqtt_hub as mqtt_hub_module
from app.services.mqtt_hub import MQTTHub
from tests.fakes import (
    FakeDeviceRepository,
    FakeLocationRepository,
    FakeSession,
    FakeSessionMaker,
    FakeTelemetryRepository,
    make_device,
    stands_in_for,
)

VALID_PAYLOAD = {"temperature": 21.5, "humidity": 44.0, "pressure": 1013.2}


class FakeMessage:
    def __init__(self, topic: str, payload):
        self.topic = topic
        if isinstance(payload, dict):
            payload = json.dumps(payload).encode()
        elif isinstance(payload, str):
            payload = payload.encode()
        self.payload = payload


def message(topic: str, payload) -> aiomqtt.Message:
    """`_handle_message` only reads .topic and .payload off the message."""
    return stands_in_for(aiomqtt.Message, FakeMessage(topic, payload))


class Harness:
    """Wires the hub's two service factories onto in-memory repositories."""

    def __init__(self, devices=(), locations=()):
        self.session = FakeSession()
        self.session_maker = FakeSessionMaker(self.session)
        self.device_repo = FakeDeviceRepository(devices)
        self.location_repo = FakeLocationRepository(locations)
        self.telemetry_repo = FakeTelemetryRepository()
        self.telemetry_service = None
        self.device_service = None

    def install(self, monkeypatch):
        from app.services.device_service import DeviceService
        from app.services.telemetry_service import TelemetryService

        def make_telemetry(session):
            self.telemetry_service = TelemetryService(
                session,
                stands_in_for(TelemetryRepository, self.telemetry_repo),
                stands_in_for(DeviceRepository, self.device_repo),
            )
            return self.telemetry_service

        def make_device_service(session):
            self.device_service = DeviceService(
                session,
                stands_in_for(DeviceRepository, self.device_repo),
                stands_in_for(LocationRepository, self.location_repo),
            )
            return self.device_service

        monkeypatch.setattr(mqtt_hub_module, "async_session_maker", self.session_maker)
        monkeypatch.setattr(mqtt_hub_module, "create_telemetry_service", make_telemetry)
        monkeypatch.setattr(mqtt_hub_module, "create_device_service", make_device_service)
        return self


@pytest.fixture
def harness(monkeypatch):
    def _build(devices=(), locations=()):
        return Harness(devices, locations).install(monkeypatch)

    return _build


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


async def test_reading_from_an_active_device_is_persisted(harness):
    h = harness([make_device(1, "pi-01", status=DeviceStatus.ACTIVE, last_seen=None)])
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", VALID_PAYLOAD))

    assert len(h.telemetry_repo.added) == 1
    record = h.telemetry_repo.added[0]
    assert record["device_id"] == 1
    assert record["climate_data"].temperature == 21.5
    assert h.session.commits >= 1


async def test_an_active_device_is_marked_online(harness):
    device = make_device(1, "pi-01", status=DeviceStatus.ACTIVE, last_seen=None, is_online=False)
    harness([device])
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", VALID_PAYLOAD))

    assert device.is_online is True
    assert device.last_seen is not None


async def test_the_hardware_id_comes_from_the_topic(harness):
    h = harness()
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-xyz/telemetry", VALID_PAYLOAD))

    assert h.device_repo.created == [("pi-xyz", 1)]


async def test_a_source_field_in_the_payload_cannot_spoof_the_topic(harness):
    h = harness([make_device(1, "pi-01", status=DeviceStatus.ACTIVE, last_seen=None)])
    hub = MQTTHub()

    payload = {**VALID_PAYLOAD, "source": "somebody-else"}
    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", payload))

    assert h.telemetry_repo.added[0]["climate_data"].source == "pi-01"


async def test_the_session_is_opened_and_closed_per_message(harness):
    h = harness([make_device(1, "pi-01", status=DeviceStatus.ACTIVE)])
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", VALID_PAYLOAD))

    assert h.session_maker.calls == 1
    assert h.session.closed is True


# --------------------------------------------------------------------------- #
# Device lifecycle gating
# --------------------------------------------------------------------------- #


async def test_an_unknown_device_is_auto_registered_as_pending(harness):
    h = harness()
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-new/telemetry", VALID_PAYLOAD))

    assert len(h.device_repo.devices) == 1
    assert h.device_repo.devices[0].status == DeviceStatus.PENDING


async def test_a_newly_registered_devices_first_reading_is_dropped(harness):
    """Auto-registration lands on `pending`, so nothing is stored until an
    operator activates the device from the Devices page."""
    h = harness()
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-new/telemetry", VALID_PAYLOAD))

    assert h.telemetry_repo.added == []


@pytest.mark.parametrize("status", [DeviceStatus.PENDING, DeviceStatus.BLOCKED])
async def test_readings_from_non_active_devices_are_dropped(harness, status):
    device = make_device(1, "pi-01", status=status, last_seen=None, is_online=False)
    h = harness([device])
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", VALID_PAYLOAD))

    assert h.telemetry_repo.added == []
    assert device.is_online is False


async def test_a_blocked_device_is_not_re_registered(harness):
    h = harness([make_device(1, "pi-01", status=DeviceStatus.BLOCKED)])
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", VALID_PAYLOAD))

    assert h.device_repo.created == []


# --------------------------------------------------------------------------- #
# Malformed input
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "payload",
    [b"not json", b"", b"{unterminated", b"\xff\xfe invalid utf8"],
    ids=["garbage", "empty", "truncated", "bad-utf8"],
)
async def test_undecodable_payloads_are_dropped_before_any_db_work(harness, payload):
    h = harness()
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", payload))

    assert h.session_maker.calls == 0
    assert h.telemetry_repo.added == []


@pytest.mark.parametrize(
    "payload",
    [
        {"temperature": 21.5},
        {"temperature": "warm", "humidity": 44.0, "pressure": 1013.2},
        {**VALID_PAYLOAD, "timestamp": "not-a-date"},
    ],
    ids=["missing-fields", "wrong-type", "bad-timestamp"],
)
async def test_payloads_that_fail_validation_never_reach_the_database(harness, payload):
    h = harness([make_device(1, "pi-01", status=DeviceStatus.ACTIVE)])
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", payload))

    assert h.session_maker.calls == 0
    assert h.telemetry_repo.added == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Valid JSON that is not an object reaches payload.pop('source', None) and "
        "raises TypeError. Nothing in _handle_message or start() catches it — the "
        "try/except in start() only covers MqttError — so any device publishing "
        "e.g. '[1,2,3]' kills the ingestion task until the process restarts."
    ),
)
@pytest.mark.parametrize(
    "payload", [b"[1, 2, 3]", b"42", b'"a string"', b"null"], ids=["array", "int", "str", "null"]
)
async def test_a_json_payload_that_is_not_an_object_is_dropped(harness, payload):
    h = harness()
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", payload))

    assert h.telemetry_repo.added == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "_handle_message indexes topic_parts[2] with no length check, so a short "
        "topic raises IndexError out of the subscribe loop. Not reachable through "
        "the 'sentinel/devices/+/telemetry' subscription today, but the handler "
        "should not depend on the broker for that guarantee."
    ),
)
async def test_a_short_topic_does_not_take_down_the_listener(harness):
    harness()
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices", VALID_PAYLOAD))


async def test_a_database_failure_is_swallowed(harness, monkeypatch):
    h = harness([make_device(1, "pi-01", status=DeviceStatus.ACTIVE)])

    async def boom(*args, **kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(h.telemetry_repo, "add_telemetry", boom)
    hub = MQTTHub()

    await hub._handle_message(message("sentinel/devices/pi-01/telemetry", VALID_PAYLOAD))

    assert h.session.closed is True


# --------------------------------------------------------------------------- #
# start()
# --------------------------------------------------------------------------- #


def test_default_topic_filter_and_host():
    hub = MQTTHub(broker_host="broker.local")

    assert hub.broker_host == "broker.local"
    assert hub.topic_filter == "sentinel/devices/+/telemetry"


def test_broker_host_defaults_to_localhost():
    assert MQTTHub().broker_host == "localhost"


async def test_start_subscribes_and_dispatches_each_message(monkeypatch):
    handled = []
    messages = [message("sentinel/devices/pi-01/telemetry", VALID_PAYLOAD)]
    subscribed: list[str] = []

    class StubClient:
        def __init__(self, host, **kwargs):
            self.host = host
            self.messages = self._iter()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def subscribe(self, topic):
            subscribed.append(topic)

        async def _iter(self):
            for message in messages:
                yield message
            raise StopHub()

    class StopHub(Exception):
        pass

    monkeypatch.setattr(aiomqtt, "Client", StubClient)
    hub = MQTTHub(broker_host="broker.local")
    monkeypatch.setattr(hub, "_handle_message", lambda m: _record(handled, m))

    with pytest.raises(StopHub):
        await hub.start()

    assert subscribed == ["sentinel/devices/+/telemetry"]
    assert handled == messages


async def test_start_retries_after_a_broker_error(monkeypatch):
    attempts = []
    sleeps = []

    class FlakyClient:
        def __init__(self, host, **kwargs):
            attempts.append(host)

        async def __aenter__(self):
            if len(attempts) < 3:
                raise aiomqtt.MqttError("broker down")
            raise KeyboardInterrupt  # break out of the infinite loop

        async def __aexit__(self, *exc):
            return False

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(aiomqtt, "Client", FlakyClient)
    monkeypatch.setattr(mqtt_hub_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        await MQTTHub(broker_host="broker.local").start()

    assert len(attempts) == 3
    assert sleeps == [5, 5]


async def _record(sink, message):
    sink.append(message)
