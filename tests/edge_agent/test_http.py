"""Agent HTTP surface.

The routes are the contract between the backend and the camera: a viewer that
disappears must release its lease, a cold sensor must produce a 503 rather than
hang, and an unknown hardware id must 404. `build_app`'s lifespan is skipped
(ASGITransport does not run it), so no capture thread is ever started.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from agent.capture import CaptureController
from agent.config import AgentSettings
from agent.http import BOUNDARY, build_app
from agent.power import PowerManager
from agent.sinks.mjpeg import MJPEGSink
from tests.fakes import stands_in_for

HARDWARE_ID = "pi_cam_test"


class StubCapture:
    def __init__(self, sensor_on: bool = False):
        self.sensor_on = sensor_on
        self.desired: list[bool] = []
        self.shutdowns = 0

    def set_desired(self, on: bool) -> None:
        self.desired.append(on)

    def shutdown(self) -> None:
        self.shutdowns += 1


def as_capture(stub: StubCapture) -> CaptureController:
    """build_app only reads sensor_on and calls shutdown() on the controller."""
    return stands_in_for(CaptureController, stub)


class ScriptedSink(MJPEGSink):
    """An MJPEGSink that hands each new viewer a canned sequence of frames."""

    def __init__(self, settings, payloads=()):
        super().__init__(settings)
        self.payloads = list(payloads)
        self.added: list[str] = []
        self.removed: list[str] = []

    def add_viewer(self, viewer_id, conn):
        super().add_viewer(viewer_id, conn)
        self.added.append(viewer_id)
        for payload in self.payloads:
            conn.offer(payload)

    def remove_viewer(self, viewer_id):
        super().remove_viewer(viewer_id)
        self.removed.append(viewer_id)


@pytest.fixture
def settings():
    return AgentSettings(hardware_id=HARDWARE_ID, lease_ttl_s=0.1, warmup_s=0.0)


@pytest.fixture
def capture():
    return StubCapture()


@pytest.fixture
def harness(settings, capture):
    def _build(payloads=()):
        sink = ScriptedSink(settings, payloads)
        power = PowerManager(settings, as_capture(capture))
        app = build_app(settings, as_capture(capture), power, sink)
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://agent")
        return client, sink, power

    return _build


# --------------------------------------------------------------------------- #
# /healthz
# --------------------------------------------------------------------------- #


async def test_healthz_reports_the_agent_state(harness, capture):
    client, _, power = harness()
    capture.sensor_on = True
    power.create_lease("viewer-1")

    async with client:
        body = (await client.get("/healthz")).json()

    assert body == {
        "status": "ok",
        "hardware_id": HARDWARE_ID,
        "sensor_on": True,
        "viewers": 1,
    }


async def test_healthz_reports_an_idle_agent(harness):
    client, _, _ = harness()

    async with client:
        body = (await client.get("/healthz")).json()

    assert body["sensor_on"] is False
    assert body["viewers"] == 0


# --------------------------------------------------------------------------- #
# Hardware id guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", ["stream", "snapshot"])
async def test_an_unknown_camera_is_a_404(harness, path):
    client, sink, power = harness()

    async with client:
        response = await client.get(f"/cameras/some-other-cam/{path}")

    assert response.status_code == 404
    assert "some-other-cam" in response.json()["detail"]
    assert power.viewer_count == 0
    assert sink.added == []


# --------------------------------------------------------------------------- #
# /snapshot
# --------------------------------------------------------------------------- #


async def test_snapshot_returns_the_first_frame_as_a_jpeg(harness):
    client, _, _ = harness(payloads=[b"jpeg-bytes"])

    async with client:
        response = await client.get(f"/cameras/{HARDWARE_ID}/snapshot")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"jpeg-bytes"


async def test_snapshot_503s_when_the_sensor_never_delivers(harness):
    """The one test that pays the real ~3s snapshot timeout, so it also asserts
    the lease is released on that path rather than duplicating the wait."""
    client, sink, power = harness()  # no payloads queued

    async with client:
        response = await client.get(f"/cameras/{HARDWARE_ID}/snapshot")

    assert response.status_code == 503
    assert "did not deliver" in response.json()["detail"]
    assert sink.removed == sink.added
    assert power.viewer_count == 0


async def test_snapshot_takes_a_lease_so_the_sensor_powers_up(harness):
    client, sink, _ = harness(payloads=[b"jpeg-bytes"])

    async with client:
        await client.get(f"/cameras/{HARDWARE_ID}/snapshot")

    assert len(sink.added) == 1
    assert sink.added[0].startswith("snapshot-")


async def test_snapshot_always_releases_its_lease(harness):
    client, sink, power = harness(payloads=[b"jpeg-bytes"])

    async with client:
        await client.get(f"/cameras/{HARDWARE_ID}/snapshot")

    assert sink.removed == sink.added
    assert power.viewer_count == 0


async def test_each_snapshot_uses_a_distinct_viewer_id(harness):
    client, sink, _ = harness(payloads=[b"jpeg-bytes"])

    async with client:
        await client.get(f"/cameras/{HARDWARE_ID}/snapshot")
        await client.get(f"/cameras/{HARDWARE_ID}/snapshot")

    assert len(set(sink.added)) == 2


# --------------------------------------------------------------------------- #
# /stream
# --------------------------------------------------------------------------- #


async def test_stream_advertises_the_multipart_content_type(harness):
    client, _, _ = harness(payloads=[b"a"])

    async with client:
        async with client.stream("GET", f"/cameras/{HARDWARE_ID}/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == (
                f"multipart/x-mixed-replace; boundary={BOUNDARY}"
            )
            await response.aclose()


async def test_stream_frames_carry_a_boundary_and_content_length(harness):
    client, _, _ = harness(payloads=[b"jpeg-bytes"])

    async with client:
        response = await client.get(f"/cameras/{HARDWARE_ID}/stream")

    body = response.content
    assert body.startswith(f"--{BOUNDARY}\r\n".encode())
    assert b"Content-Type: image/jpeg\r\n" in body
    assert b"Content-Length: 10\r\n" in body
    assert body.endswith(b"jpeg-bytes\r\n")


async def test_stream_ends_when_a_full_ttl_passes_with_no_frame(harness):
    """A zombie connection whose lease already expired is closed rather than held."""
    client, _, power = harness(payloads=[b"one"])

    async with client:
        response = await asyncio.wait_for(
            client.get(f"/cameras/{HARDWARE_ID}/stream"), timeout=5.0
        )

    assert response.content.endswith(b"one\r\n")
    assert power.viewer_count == 0


async def test_stream_releases_its_lease_when_the_generator_finishes(harness):
    client, sink, power = harness(payloads=[b"one"])

    async with client:
        await client.get(f"/cameras/{HARDWARE_ID}/stream")

    assert sink.removed == sink.added
    assert power.viewer_count == 0


async def test_stream_with_no_frames_at_all_closes_cleanly(harness):
    client, sink, power = harness()

    async with client:
        response = await asyncio.wait_for(
            client.get(f"/cameras/{HARDWARE_ID}/stream"), timeout=5.0
        )

    assert response.status_code == 200
    assert response.content == b""
    assert sink.removed == sink.added
    assert power.viewer_count == 0


async def test_each_stream_viewer_gets_its_own_id(harness):
    client, sink, _ = harness(payloads=[b"one"])

    async with client:
        await client.get(f"/cameras/{HARDWARE_ID}/stream")
        await client.get(f"/cameras/{HARDWARE_ID}/stream")

    assert len(set(sink.added)) == 2
