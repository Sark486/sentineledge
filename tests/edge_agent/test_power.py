"""PowerManager decides when the camera sensor is powered.

Time is injected into `tick()`/`sensor_needed()` as `now`, so every scenario
below is exact — no sleeping, no wall-clock tolerance. `create_lease` and
`renew_lease` do read `time.monotonic()` directly, so those tests work in
relative terms against a real (but frozen-enough) clock.
"""

import time

import pytest

from agent.capture import CaptureController
from agent.config import AgentSettings
from agent.power import PowerManager
from tests.fakes import stands_in_for


class StubCapture:
    def __init__(self):
        self.desired: list[bool] = []
        self.sensor_on = False

    def set_desired(self, on: bool) -> None:
        self.desired.append(on)


def as_capture(stub: StubCapture) -> CaptureController:
    """PowerManager only ever calls set_desired on the controller."""
    return stands_in_for(CaptureController, stub)


@pytest.fixture
def settings():
    return AgentSettings(lease_ttl_s=5.0, power_off_grace_s=10.0)


@pytest.fixture
def capture():
    return StubCapture()


@pytest.fixture
def power(settings, capture):
    return PowerManager(settings, as_capture(capture))


# --------------------------------------------------------------------------- #
# Leases
# --------------------------------------------------------------------------- #


def test_a_new_manager_wants_nothing_powered(power):
    assert power.viewer_count == 0
    assert power.sensor_needed(time.monotonic()) is False


def test_creating_a_lease_counts_as_a_write(power):
    """Otherwise the very first lease would expire before the sensor could
    deliver the frame that renews it."""
    power.create_lease("viewer-1")

    assert power.viewer_count == 1
    assert power.sensor_needed(time.monotonic()) is True


def test_dropping_a_lease_removes_it(power):
    power.create_lease("viewer-1")
    power.drop_lease("viewer-1")

    assert power.viewer_count == 0


def test_dropping_an_unknown_lease_is_harmless(power):
    power.drop_lease("never-existed")

    assert power.viewer_count == 0


def test_creating_the_same_viewer_twice_does_not_double_count(power):
    power.create_lease("viewer-1")
    power.create_lease("viewer-1")

    assert power.viewer_count == 1


def test_renewing_an_unknown_lease_does_not_resurrect_it(power):
    power.renew_lease("never-existed")

    assert power.viewer_count == 0


def test_a_lease_ages_out_after_the_ttl(power):
    power.create_lease("viewer-1")
    now = time.monotonic()

    assert power.sensor_needed(now + 4.9) is True
    assert power.sensor_needed(now + 5.1) is False


def test_renewing_a_lease_extends_it(power):
    power.create_lease("viewer-1")
    power.renew_lease("viewer-1")

    assert power.sensor_needed(time.monotonic() + 4.0) is True


def test_one_live_viewer_keeps_the_sensor_needed(power):
    power.create_lease("live")
    power.create_lease("stale")
    power._leases["stale"].last_write -= 100

    assert power.sensor_needed(time.monotonic()) is True


def test_stale_leases_are_reaped_on_tick(power, capture):
    power.create_lease("viewer-1")
    power._leases["viewer-1"].last_write -= 100

    power.tick(time.monotonic())

    assert power.viewer_count == 0


# --------------------------------------------------------------------------- #
# Other power sources
# --------------------------------------------------------------------------- #


def test_armed_keeps_the_sensor_needed_with_no_viewers(power):
    power.armed = True

    assert power.sensor_needed(time.monotonic()) is True


def test_a_cue_keeps_the_sensor_needed_until_it_expires(power):
    now = time.monotonic()
    power.cue_until = now + 10

    assert power.sensor_needed(now + 5) is True
    assert power.sensor_needed(now + 11) is False


def test_an_unset_cue_is_not_a_power_source(power):
    assert power.cue_until is None
    assert power.sensor_needed(time.monotonic()) is False


# --------------------------------------------------------------------------- #
# tick(): power-on and the grace period
# --------------------------------------------------------------------------- #


def test_tick_powers_the_sensor_on_for_a_viewer(power, capture):
    power.create_lease("viewer-1")

    power.tick(time.monotonic())

    assert capture.desired == [True]


def test_tick_does_not_power_on_when_nothing_needs_the_sensor(power, capture):
    power.tick(time.monotonic())

    assert capture.desired == []


def test_the_sensor_is_held_through_the_grace_period(power, capture):
    now = time.monotonic()
    power.create_lease("viewer-1")
    power.tick(now)

    # The viewer disappears; the sensor must not drop immediately.
    power.drop_lease("viewer-1")
    power.tick(now + 1)
    power.tick(now + 9)

    assert capture.desired == [True]


def test_the_sensor_is_released_once_the_grace_period_elapses(power, capture):
    now = time.monotonic()
    power.create_lease("viewer-1")
    power.tick(now)
    power.drop_lease("viewer-1")

    power.tick(now + 1)  # arms the grace deadline at now+11
    power.tick(now + 12)

    assert capture.desired == [True, False]


def test_a_viewer_returning_inside_the_grace_period_cancels_the_release(power, capture):
    """An F5 must not power-cycle the sensor."""
    now = time.monotonic()
    power.create_lease("viewer-1")
    power.tick(now)
    power.drop_lease("viewer-1")
    power.tick(now + 1)

    power.create_lease("viewer-2")
    power.tick(now + 2)
    power.tick(now + 30)

    assert capture.desired == [True, True]
    assert False not in capture.desired


def test_the_grace_period_restarts_after_a_second_departure(power, capture):
    now = time.monotonic()
    power.create_lease("viewer-1")
    power.tick(now)
    power.drop_lease("viewer-1")
    power.tick(now + 1)
    power.create_lease("viewer-2")
    power.tick(now + 2)
    power.drop_lease("viewer-2")

    power.tick(now + 3)  # re-arms, deadline now+13
    power.tick(now + 12)
    assert capture.desired.count(False) == 0

    power.tick(now + 14)
    assert capture.desired[-1] is False


def test_ticking_while_already_off_does_not_re_release(power, capture):
    now = time.monotonic()
    power.create_lease("viewer-1")
    power.tick(now)
    power.drop_lease("viewer-1")
    power.tick(now + 1)
    power.tick(now + 12)

    power.tick(now + 20)
    power.tick(now + 30)

    assert capture.desired == [True, False]


def test_an_expired_lease_alone_triggers_the_release_path(power, capture):
    """A viewer whose socket died stops renewing; the reap plus grace period is
    what actually powers the sensor down."""
    now = time.monotonic()
    power.create_lease("viewer-1")
    power.tick(now)
    power._leases["viewer-1"].last_write -= 100

    power.tick(now + 1)
    power.tick(now + 12)

    assert capture.desired == [True, False]
    assert power.viewer_count == 0


def test_grace_period_length_comes_from_settings(capture):
    settings = AgentSettings(lease_ttl_s=5.0, power_off_grace_s=60.0)
    power = PowerManager(settings, as_capture(capture))
    now = time.monotonic()
    power.create_lease("viewer-1")
    power.tick(now)
    power.drop_lease("viewer-1")

    power.tick(now + 1)
    power.tick(now + 30)
    assert capture.desired == [True]

    power.tick(now + 62)
    assert capture.desired == [True, False]


def test_lease_ttl_comes_from_settings(capture):
    power = PowerManager(AgentSettings(lease_ttl_s=1.0), as_capture(capture))
    power.create_lease("viewer-1")
    now = time.monotonic()

    assert power.sensor_needed(now + 0.5) is True
    assert power.sensor_needed(now + 1.5) is False
