"""Process wiring: `main()` and `build_app`'s lifespan.

Together these are the only place the agent's four components are connected, so
a mis-wire here (a sink never registered on the bus, a power loop never started)
would leave the camera silently dead in production.
"""

import asyncio

import pytest

from agent import __main__ as agent_main
from agent.capture import CaptureController
from agent.config import AgentSettings
from agent.http import build_app
from agent.power import PowerManager
from agent.sinks.base import SlotWorkerSink
from agent.sinks.mjpeg import MJPEGSink
from tests.fakes import stands_in_for


class StubCapture:
    """Only set_desired/shutdown/sensor_on are ever touched, and building a real
    CaptureController would start a camera thread."""

    def __init__(self):
        self.sensor_on = False
        self.desired: list[bool] = []
        self.shutdowns = 0

    def set_desired(self, on: bool) -> None:
        self.desired.append(on)

    def shutdown(self) -> None:
        self.shutdowns += 1


def as_capture(stub: StubCapture) -> CaptureController:
    return stands_in_for(CaptureController, stub)


def as_sink(stub: SlotWorkerSink) -> MJPEGSink:
    """The lifespan only start()s and stop()s the sink."""
    return stands_in_for(MJPEGSink, stub)


# --------------------------------------------------------------------------- #
# main()
# --------------------------------------------------------------------------- #


class RecordingBus:
    """Stands in for FrameBus so the test can see what main() registered."""

    instances: list["RecordingBus"] = []

    def __init__(self):
        self.sinks = []
        RecordingBus.instances.append(self)

    def register(self, sink):
        self.sinks.append(sink)

    def publish(self, frame):
        pass


@pytest.fixture
def run_main(monkeypatch):
    """Runs main() with the camera and the server replaced, returning what it built."""

    def _run():
        captured: dict = {}
        RecordingBus.instances.clear()

        def fake_build_app(settings, capture, power, mjpeg):
            captured["components"] = (settings, capture, power, mjpeg)
            return "the-app"

        def fake_run(app, **kwargs):
            captured["run_app"] = app
            captured["run_kwargs"] = kwargs

        monkeypatch.setattr(agent_main, "FrameBus", RecordingBus)
        monkeypatch.setattr(agent_main, "CaptureController", lambda bus: as_capture(StubCapture()))
        monkeypatch.setattr(agent_main, "build_app", fake_build_app)
        monkeypatch.setattr(agent_main.uvicorn, "run", fake_run)

        agent_main.main()
        captured["bus"] = RecordingBus.instances[0]
        return captured

    return _run


def test_main_registers_the_mjpeg_sink_on_the_bus(run_main):
    """Without this the capture thread publishes frames that reach no encoder."""
    captured = run_main()

    _, _, _, mjpeg = captured["components"]
    assert isinstance(mjpeg, MJPEGSink)
    assert captured["bus"].sinks == [mjpeg]


def test_main_builds_a_power_manager_over_the_capture_controller(run_main):
    captured = run_main()

    _, capture, power, _ = captured["components"]
    assert isinstance(power, PowerManager)
    assert power._capture is capture


def test_main_serves_the_built_app(run_main):
    captured = run_main()

    assert captured["run_app"] == "the-app"
    assert captured["run_kwargs"]["host"] == "0.0.0.0"


def test_main_serves_on_the_configured_port(run_main, monkeypatch):
    monkeypatch.setenv("AGENT_HTTP_PORT", "9123")

    captured = run_main()

    assert captured["run_kwargs"]["port"] == 9123


def test_main_reads_the_hardware_id_from_the_environment(run_main, monkeypatch):
    monkeypatch.setenv("AGENT_HARDWARE_ID", "pi_cam_kitchen")

    captured = run_main()

    assert captured["components"][0].hardware_id == "pi_cam_kitchen"


def test_main_defaults_the_hardware_id(run_main):
    captured = run_main()

    assert captured["components"][0].hardware_id == "pi_cam_0"


# --------------------------------------------------------------------------- #
# build_app lifespan
# --------------------------------------------------------------------------- #


class TrackingSink(SlotWorkerSink):
    name = "tracking"

    def __init__(self):
        super().__init__()
        self.starts = 0
        self.stops = 0

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> None:
        self.stops += 1

    def add_viewer(self, viewer_id, conn):
        pass

    def remove_viewer(self, viewer_id):
        pass


@pytest.fixture
def settings():
    return AgentSettings(hardware_id="pi_cam_test")


async def test_lifespan_starts_the_sink_and_the_power_loop(settings, monkeypatch):
    ticks = asyncio.Event()
    capture = StubCapture()
    sink = TrackingSink()
    power = PowerManager(settings, as_capture(capture))
    monkeypatch.setattr(power, "tick", lambda now: ticks.set())
    monkeypatch.setattr("agent.power.TICK_S", 0.01)
    app = build_app(settings, as_capture(capture), power, as_sink(sink))

    async with app.router.lifespan_context(app):
        assert sink.starts == 1
        await asyncio.wait_for(ticks.wait(), timeout=2.0)

    assert sink.stops == 1


async def test_lifespan_shuts_the_capture_thread_down(settings):
    capture = StubCapture()
    sink = TrackingSink()
    app = build_app(settings, as_capture(capture), PowerManager(settings, as_capture(capture)), as_sink(sink))

    async with app.router.lifespan_context(app):
        pass

    assert capture.shutdowns == 1


async def test_lifespan_cancels_the_power_loop(settings, monkeypatch):
    capture = StubCapture()
    sink = TrackingSink()
    power = PowerManager(settings, as_capture(capture))
    started = asyncio.Event()

    async def fake_run():
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(power, "run", fake_run)
    app = build_app(settings, as_capture(capture), power, as_sink(sink))

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), timeout=2.0)

    # A leaked task would keep ticking after shutdown; nothing should remain.
    running = [getattr(t.get_coro(), "__name__", "") for t in asyncio.all_tasks()]
    assert "fake_run" not in running


async def test_power_run_ticks_on_a_schedule(settings, monkeypatch):
    capture = StubCapture()
    power = PowerManager(settings, as_capture(capture))
    seen: list[float] = []
    monkeypatch.setattr(power, "tick", lambda now: seen.append(now))
    monkeypatch.setattr("agent.power.TICK_S", 0.001)

    task = asyncio.create_task(power.run())
    await asyncio.sleep(0.05)
    task.cancel()

    assert len(seen) >= 2
