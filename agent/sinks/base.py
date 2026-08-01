import logging
import threading
from typing import Protocol

from agent.frames import Frame, LatestSlot

logger = logging.getLogger(__name__)


class FrameSink(Protocol):
    def on_frame(self, frame: Frame) -> None:
        """Called from the capture thread — MUST be non-blocking."""
        ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


class SlotWorkerSink:
    """FrameSink base: a LatestSlot fed by the capture thread, drained by an
    owned worker thread. Subclasses implement `_process(frame)`."""

    name = "sink"

    def __init__(self) -> None:
        self._slot = LatestSlot()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def on_frame(self, frame: Frame) -> None:
        self._slot.put(frame)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            frame = self._slot.get(timeout=0.5)
            if frame is None:
                continue
            try:
                self._process(frame)
            except Exception:
                logger.exception("%s sink failed on frame %d", self.name, frame.seq)

    def _process(self, frame: Frame) -> None:
        raise NotImplementedError
