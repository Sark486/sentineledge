import threading
from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class Frame:
    seq: int
    ts: float
    main: np.ndarray  # (480, 640, 3), BGR channel order (libcamera "RGB888")
    lores_y: np.ndarray  # (240, 320) luma plane, stride padding already sliced off


class LatestSlot:
    """Single-slot, drop-oldest mailbox.

    A writer overwrites whatever is pending; a slow reader misses frames.
    Deliberately not a queue: a queue either grows unboundedly or blocks the
    capture thread, and both are worse than dropping already-stale frames.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._item: Frame | None = None

    def put(self, item: Frame) -> None:
        with self._cond:
            self._item = item
            self._cond.notify()

    def get(self, timeout: float) -> Frame | None:
        """Take the pending frame, waiting up to `timeout`. None on timeout."""
        with self._cond:
            if self._item is None:
                self._cond.wait(timeout)
            item, self._item = self._item, None
            return item
