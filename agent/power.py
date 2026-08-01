import asyncio
import logging
import time
from dataclasses import dataclass

from agent.capture import CaptureController
from agent.config import AgentSettings

logger = logging.getLogger(__name__)

TICK_S = 1.0


@dataclass
class ViewerLease:
    id: str
    last_write: float  # monotonic; bumped only by a successful frame write


class PowerManager:
    """Decides whether the sensor is needed. Deliberately no viewer refcount:
    "viewer exists" is derived from observable liveness (a recent successful
    write to that viewer's socket), so no code path can leak a viewer — a dead
    one simply stops renewing and its lease ages out after LEASE_TTL.
    """

    def __init__(self, settings: AgentSettings, capture: CaptureController) -> None:
        self._settings = settings
        self._capture = capture
        self._leases: dict[str, ViewerLease] = {}
        # Three power sources; armed and cue are always False in this milestone.
        self.armed = False
        self.cue_until: float | None = None
        self._powered = False  # what we last told the capture controller
        self._grace_deadline: float | None = None

    def create_lease(self, viewer_id: str) -> None:
        # Creation counts as a write: the sensor must come on before the first
        # real frame can ever be written, or no lease would survive startup.
        self._leases[viewer_id] = ViewerLease(id=viewer_id, last_write=time.monotonic())
        logger.info("lease created: %s (%d total)", viewer_id, len(self._leases))

    def renew_lease(self, viewer_id: str) -> None:
        lease = self._leases.get(viewer_id)
        if lease is not None:
            lease.last_write = time.monotonic()

    def drop_lease(self, viewer_id: str) -> None:
        if self._leases.pop(viewer_id, None) is not None:
            logger.info("lease dropped: %s (%d left)", viewer_id, len(self._leases))

    @property
    def viewer_count(self) -> int:
        return len(self._leases)

    def sensor_needed(self, now: float) -> bool:
        return (
            self.armed
            or (self.cue_until is not None and now < self.cue_until)
            or any(
                now - lease.last_write < self._settings.lease_ttl_s
                for lease in self._leases.values()
            )
        )

    def _reap_stale(self, now: float) -> None:
        stale = [
            lease.id
            for lease in self._leases.values()
            if now - lease.last_write >= self._settings.lease_ttl_s
        ]
        for viewer_id in stale:
            del self._leases[viewer_id]
            logger.info("lease expired: %s", viewer_id)

    async def run(self) -> None:
        while True:
            # A raise here would end power management for the life of the
            # process, leaving the sensor stuck in whatever state it was last
            # told. Log and keep ticking instead.
            try:
                self.tick(time.monotonic())
            except Exception:
                logger.exception("power tick failed")
            await asyncio.sleep(TICK_S)

    def tick(self, now: float) -> None:
        self._reap_stale(now)
        if self.sensor_needed(now):
            self._grace_deadline = None
            self._powered = True
            self._capture.set_desired(True)
        elif self._powered:
            # Hysteresis: hold the sensor for POWER_OFF_GRACE after the last
            # lease dies so an F5 doesn't power-cycle it.
            if self._grace_deadline is None:
                self._grace_deadline = now + self._settings.power_off_grace_s
                logger.info(
                    "no power source; releasing sensor in %.0fs",
                    self._settings.power_off_grace_s,
                )
            elif now >= self._grace_deadline:
                self._grace_deadline = None
                self._powered = False
                self._capture.set_desired(False)
