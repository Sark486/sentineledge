import logging
import threading
import time

from agent.frames import Frame
from agent.sinks.base import FrameSink

logger = logging.getLogger(__name__)

MAIN_SIZE = (640, 480)
LORES_SIZE = (320, 240)
# 66666µs per frame = 15fps cap
FRAME_DURATION_US = 66666


class FrameBus:
    def __init__(self) -> None:
        self._sinks: list[FrameSink] = []

    def register(self, sink: FrameSink) -> None:
        self._sinks.append(sink)

    def publish(self, frame: Frame) -> None:
        for sink in self._sinks:
            sink.on_frame(frame)


class CaptureController:
    """Owns the sensor via a single long-lived camera thread.

    The asyncio side (PowerManager) only flips `set_desired()`; the thread
    reconciles - opening Picamera2, capturing, and closing all happen off the
    event loop because `capture_array()` and sensor open/close block.
    """

    def __init__(self, bus: FrameBus) -> None:
        self._bus = bus
        self._cond = threading.Condition()
        self._desired = False
        self._shutdown = False
        self._sensor_on = False  # true once the sensor is delivering frames
        self._thread = threading.Thread(target=self._run, name="capture", daemon=True)
        self._thread.start()

    @property
    def sensor_on(self) -> bool:
        return self._sensor_on

    def set_desired(self, on: bool) -> None:
        with self._cond:
            self._desired = on
            self._cond.notify()

    def shutdown(self) -> None:
        with self._cond:
            self._shutdown = True
            self._desired = False
            self._cond.notify()
        self._thread.join(timeout=5.0)

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._desired and not self._shutdown:
                    self._cond.wait()
                if self._shutdown:
                    return
            try:
                self._capture_cycle()
            except Exception:
                logger.exception("capture cycle crashed; sensor closed")
                # Avoid a tight crash loop if the camera is wedged.
                time.sleep(2.0)

    def _capture_cycle(self) -> None:
        from picamera2 import Picamera2

        picam2 = Picamera2()
        started = False
        try:
            config = picam2.create_video_configuration(
                main={"size": MAIN_SIZE, "format": "RGB888"},
                lores={"size": LORES_SIZE, "format": "YUV420"},
                controls={"FrameDurationLimits": (FRAME_DURATION_US, FRAME_DURATION_US)},
            )
            picam2.configure(config)
            opened = time.monotonic()
            picam2.start()
            started = True
            seq = 0
            while True:
                with self._cond:
                    if not self._desired or self._shutdown:
                        return
                # Blocks until the next frame — this is why we live on a thread.
                arrays, _metadata = picam2.capture_arrays(["main", "lores"])
                main, lores = arrays
                if seq == 0:
                    self._sensor_on = True
                    logger.info(
                        "sensor delivering frames (first frame after %.2fs)",
                        time.monotonic() - opened,
                    )
                # YUV420 comes back (h*3/2, stride-aligned w) = (360, 384);
                # the valid Y plane is the top-left (240, 320) crop. Slicing
                # rows only would keep 64 columns of stride padding.
                lores_y = lores[: LORES_SIZE[1], : LORES_SIZE[0]]
                self._bus.publish(Frame(seq=seq, ts=time.time(), main=main, lores_y=lores_y))
                seq += 1
        finally:
            self._sensor_on = False
            # configure()/start() can raise, and stopping a camera that never
            # started raises again from inside the finally, masking the original.
            if started:
                picam2.stop()
            picam2.close()
            logger.info("sensor released")
