import asyncio
import threading

import cv2

from agent.config import AgentSettings
from agent.frames import Frame
from agent.sinks.base import SlotWorkerSink


class ViewerConnection:
    """Asyncio-side mailbox for one MJPEG viewer. The sink's worker thread
    offers encoded bytes; the HTTP handler's generator awaits them. Handoff
    crosses thread→loop only via call_soon_threadsafe."""

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._event = asyncio.Event()
        self._payload: bytes | None = None

    def offer(self, jpeg: bytes) -> None:
        """Called from the sink worker thread. Drop-oldest: overwrites."""
        self._payload = jpeg
        self._loop.call_soon_threadsafe(self._event.set)

    async def next_jpeg(self, timeout: float) -> bytes | None:
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
        except TimeoutError:
            return None
        self._event.clear()
        return self._payload


class MJPEGSink(SlotWorkerSink):
    name = "mjpeg"

    def __init__(self, settings: AgentSettings) -> None:
        super().__init__()
        self._quality = settings.jpeg_quality
        self._viewers: dict[str, ViewerConnection] = {}
        self._lock = threading.Lock()

    def add_viewer(self, viewer_id: str, conn: ViewerConnection) -> None:
        with self._lock:
            self._viewers[viewer_id] = conn

    def remove_viewer(self, viewer_id: str) -> None:
        with self._lock:
            self._viewers.pop(viewer_id, None)

    def _process(self, frame: Frame) -> None:
        with self._lock:
            viewers = list(self._viewers.values())
        if not viewers:
            return
        # frame.main is already BGR-ordered (libcamera "RGB888" is little-endian),
        # which is exactly what imencode expects — no cvtColor.
        ok, buf = cv2.imencode(".jpg", frame.main, [cv2.IMWRITE_JPEG_QUALITY, self._quality])
        if not ok:
            return
        # Encode once, fan the same bytes to every viewer.
        jpeg = buf.tobytes()
        for conn in viewers:
            conn.offer(jpeg)
