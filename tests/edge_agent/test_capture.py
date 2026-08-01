"""CaptureController's reconcile loop.

`_capture_cycle` needs a real Picamera2 and is not exercised here; every test
substitutes it. What is under test is the thread contract around it: the loop
idles until something wants the sensor, reopens after a crash without spinning,
and shuts down cleanly.
"""

import threading
import time

import numpy as np
import pytest

from agent import capture as capture_module
from agent.capture import FRAME_DURATION_US, LORES_SIZE, MAIN_SIZE, CaptureController, FrameBus
from agent.frames import Frame


class StubSink:
    def __init__(self):
        self.frames: list[Frame] = []

    def on_frame(self, frame: Frame) -> None:
        self.frames.append(frame)


class FakeController(CaptureController):
    """Replaces the Picamera2 cycle with a controllable stand-in."""

    def __init__(self, bus, cycle=None):
        self.cycles = 0
        self.cycle_ran = threading.Event()
        self._cycle = cycle
        super().__init__(bus)

    def _capture_cycle(self) -> None:
        self.cycles += 1
        self.cycle_ran.set()
        if self._cycle:
            self._cycle(self)
        else:
            # Stay "open" until something clears the desire, like the real loop.
            while True:
                with self._cond:
                    if not self._desired or self._shutdown:
                        return
                time.sleep(0.005)


@pytest.fixture
def bus():
    return FrameBus()


@pytest.fixture
def controller(bus):
    ctrl = FakeController(bus)
    yield ctrl
    ctrl.shutdown()


# --------------------------------------------------------------------------- #
# FrameBus
# --------------------------------------------------------------------------- #


def test_bus_publishes_to_every_registered_sink(bus):
    first, second = StubSink(), StubSink()
    bus.register(first)
    bus.register(second)
    frame = Frame(seq=0, ts=0.0, main=np.zeros((2, 2, 3)), lores_y=np.zeros((2, 2)))

    bus.publish(frame)

    assert first.frames == [frame]
    assert second.frames == [frame]


def test_bus_with_no_sinks_is_a_noop(bus):
    bus.publish(Frame(seq=0, ts=0.0, main=np.zeros((2, 2, 3)), lores_y=np.zeros((2, 2))))


# --------------------------------------------------------------------------- #
# Reconcile loop
# --------------------------------------------------------------------------- #


def test_the_sensor_stays_closed_until_something_wants_it(controller):
    time.sleep(0.05)

    assert controller.cycles == 0
    assert controller.sensor_on is False


def test_setting_desired_opens_the_sensor(controller):
    controller.set_desired(True)

    assert controller.cycle_ran.wait(timeout=2.0)
    assert controller.cycles == 1


def test_clearing_desired_closes_the_sensor(controller):
    controller.set_desired(True)
    assert controller.cycle_ran.wait(timeout=2.0)

    controller.set_desired(False)
    time.sleep(0.1)

    assert controller.cycles == 1


def test_the_sensor_reopens_after_a_power_cycle(controller):
    controller.set_desired(True)
    assert controller.cycle_ran.wait(timeout=2.0)
    controller.set_desired(False)
    time.sleep(0.05)

    controller.cycle_ran.clear()
    controller.set_desired(True)

    assert controller.cycle_ran.wait(timeout=2.0)
    assert controller.cycles == 2


def test_a_crashing_cycle_is_retried_after_a_backoff(bus, monkeypatch):
    """A wedged camera must not become a tight crash loop that pegs the CPU."""
    sleeps: list[float] = []
    monkeypatch.setattr(capture_module.time, "sleep", lambda s: sleeps.append(s))
    attempts = threading.Event()
    calls = {"n": 0}

    def explode(_self):
        calls["n"] += 1
        if calls["n"] >= 2:
            attempts.set()
        raise RuntimeError("camera wedged")

    ctrl = FakeController(bus, cycle=explode)
    try:
        ctrl.set_desired(True)
        assert attempts.wait(timeout=2.0)
    finally:
        ctrl.shutdown()

    assert sleeps and sleeps[0] == 2.0


def test_shutdown_stops_an_idle_controller(bus):
    ctrl = FakeController(bus)

    ctrl.shutdown()

    assert ctrl._thread.is_alive() is False


def test_shutdown_stops_a_running_controller(bus):
    ctrl = FakeController(bus)
    ctrl.set_desired(True)
    assert ctrl.cycle_ran.wait(timeout=2.0)

    ctrl.shutdown()

    assert ctrl._thread.is_alive() is False


def test_shutdown_clears_the_desire(bus):
    ctrl = FakeController(bus)
    ctrl.set_desired(True)
    assert ctrl.cycle_ran.wait(timeout=2.0)

    ctrl.shutdown()

    assert ctrl._desired is False


def test_the_capture_thread_is_a_daemon(controller):
    """The agent process must be able to exit without joining the camera thread."""
    assert controller._thread.daemon is True


def test_capture_geometry_matches_the_frame_contract():
    """frames.Frame documents these shapes; the lores crop depends on them."""
    assert MAIN_SIZE == (640, 480)
    assert LORES_SIZE == (320, 240)
    assert round(1_000_000 / FRAME_DURATION_US) == 15
