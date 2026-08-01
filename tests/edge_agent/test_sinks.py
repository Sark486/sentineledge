"""Sink tests.

`SlotWorkerSink` owns a worker thread, so these use short real timeouts rather
than fake clocks; each one joins its thread before asserting. `MJPEGSink` is
exercised with real cv2 encoding on a tiny frame — mocking imencode would test
nothing that matters here.
"""

import asyncio
import threading
import time

import numpy as np
import pytest

from agent.config import AgentSettings
from agent.frames import Frame
from agent.sinks.base import SlotWorkerSink
from agent.sinks.mjpeg import MJPEGSink, ViewerConnection


def make_frame(seq: int = 0, colour: int = 128) -> Frame:
    return Frame(
        seq=seq,
        ts=time.time(),
        main=np.full((48, 64, 3), colour, dtype=np.uint8),
        lores_y=np.full((24, 32), colour, dtype=np.uint8),
    )


class RecordingSink(SlotWorkerSink):
    name = "recording"

    def __init__(self, on_process=None):
        super().__init__()
        self.processed: list[int] = []
        self.saw_frame = threading.Event()
        self._on_process = on_process

    def _process(self, frame: Frame) -> None:
        if self._on_process:
            self._on_process(frame)
        self.processed.append(frame.seq)
        self.saw_frame.set()


# --------------------------------------------------------------------------- #
# SlotWorkerSink
# --------------------------------------------------------------------------- #


def test_the_worker_drains_frames_offered_to_the_sink():
    sink = RecordingSink()
    sink.start()
    try:
        sink.on_frame(make_frame(1))
        assert sink.saw_frame.wait(timeout=2.0)
    finally:
        sink.stop()

    assert sink.processed == [1]


def test_on_frame_does_not_block_before_the_worker_starts():
    """`on_frame` runs on the capture thread and must never block it."""
    sink = RecordingSink()

    started = time.monotonic()
    sink.on_frame(make_frame(1))

    assert time.monotonic() - started < 0.1
    assert sink.processed == []


def test_stop_joins_the_worker():
    sink = RecordingSink()
    sink.start()
    sink.stop()

    assert sink._thread is None


def test_start_is_idempotent():
    sink = RecordingSink()
    sink.start()
    first = sink._thread
    sink.start()
    try:
        assert sink._thread is first
    finally:
        sink.stop()


def test_a_sink_can_be_restarted():
    sink = RecordingSink()
    sink.start()
    sink.stop()
    sink.start()
    try:
        sink.on_frame(make_frame(2))
        assert sink.saw_frame.wait(timeout=2.0)
    finally:
        sink.stop()

    assert sink.processed == [2]


def test_stopping_a_sink_that_never_started_is_harmless():
    RecordingSink().stop()


def test_a_failing_frame_does_not_kill_the_worker():
    """One bad frame must not silently take the sink offline for the rest of the run."""
    failures = {"count": 0}

    def explode_once(frame: Frame) -> None:
        if failures["count"] == 0:
            failures["count"] += 1
            raise RuntimeError("encode blew up")

    sink = RecordingSink(on_process=explode_once)
    sink.start()
    try:
        sink.on_frame(make_frame(1))
        time.sleep(0.2)
        sink.saw_frame.clear()
        sink.on_frame(make_frame(2))
        assert sink.saw_frame.wait(timeout=2.0)
    finally:
        sink.stop()

    assert sink.processed == [2]
    assert failures["count"] == 1


# --------------------------------------------------------------------------- #
# ViewerConnection
# --------------------------------------------------------------------------- #


async def test_viewer_connection_delivers_an_offered_payload():
    conn = ViewerConnection()
    conn.offer(b"jpeg-bytes")

    assert await conn.next_jpeg(timeout=1.0) == b"jpeg-bytes"


async def test_viewer_connection_times_out_to_none():
    conn = ViewerConnection()

    assert await conn.next_jpeg(timeout=0.05) is None


async def test_viewer_connection_drops_the_older_payload():
    conn = ViewerConnection()
    conn.offer(b"old")
    conn.offer(b"new")

    assert await conn.next_jpeg(timeout=1.0) == b"new"


async def test_viewer_connection_blocks_again_after_a_delivery():
    conn = ViewerConnection()
    conn.offer(b"one")

    assert await conn.next_jpeg(timeout=1.0) == b"one"
    assert await conn.next_jpeg(timeout=0.05) is None


async def test_viewer_connection_accepts_an_offer_from_another_thread():
    """The sink's worker thread offers; only call_soon_threadsafe crosses over."""
    conn = ViewerConnection()

    threading.Thread(target=lambda: (time.sleep(0.05), conn.offer(b"threaded"))).start()

    assert await conn.next_jpeg(timeout=2.0) == b"threaded"


# --------------------------------------------------------------------------- #
# MJPEGSink
# --------------------------------------------------------------------------- #


@pytest.fixture
def mjpeg():
    sink = MJPEGSink(AgentSettings(jpeg_quality=60))
    yield sink
    sink.stop()


def test_mjpeg_does_no_work_without_viewers(mjpeg):
    """Encoding for nobody would burn CPU on a Pi for every captured frame."""
    mjpeg._process(make_frame(1))  # must not raise; nothing to assert beyond that


async def test_mjpeg_encodes_a_frame_to_jpeg_for_a_viewer(mjpeg):
    conn = ViewerConnection()
    mjpeg.add_viewer("viewer-1", conn)

    mjpeg._process(make_frame(1))
    jpeg = await conn.next_jpeg(timeout=1.0)

    assert jpeg is not None
    assert jpeg.startswith(b"\xff\xd8"), "expected a JPEG SOI marker"
    assert jpeg.endswith(b"\xff\xd9"), "expected a JPEG EOI marker"


async def test_mjpeg_fans_the_same_bytes_out_to_every_viewer(mjpeg):
    """One encode per frame, not one per viewer."""
    first, second = ViewerConnection(), ViewerConnection()
    mjpeg.add_viewer("a", first)
    mjpeg.add_viewer("b", second)

    mjpeg._process(make_frame(1))

    a = await first.next_jpeg(timeout=1.0)
    b = await second.next_jpeg(timeout=1.0)
    assert a is b


async def test_mjpeg_stops_sending_to_a_removed_viewer(mjpeg):
    conn = ViewerConnection()
    mjpeg.add_viewer("viewer-1", conn)
    mjpeg.remove_viewer("viewer-1")

    mjpeg._process(make_frame(1))

    assert await conn.next_jpeg(timeout=0.05) is None


def test_mjpeg_removing_an_unknown_viewer_is_harmless(mjpeg):
    mjpeg.remove_viewer("never-existed")


async def test_mjpeg_end_to_end_through_the_worker_thread(mjpeg):
    conn = ViewerConnection()
    mjpeg.add_viewer("viewer-1", conn)
    mjpeg.start()

    mjpeg.on_frame(make_frame(1))
    jpeg = await asyncio.wait_for(conn.next_jpeg(timeout=3.0), timeout=5.0)

    assert jpeg is not None and jpeg.startswith(b"\xff\xd8")


def test_mjpeg_quality_comes_from_settings():
    assert MJPEGSink(AgentSettings(jpeg_quality=35))._quality == 35


async def test_mjpeg_skips_the_frame_when_encoding_fails(mjpeg, monkeypatch):
    conn = ViewerConnection()
    mjpeg.add_viewer("viewer-1", conn)
    monkeypatch.setattr("agent.sinks.mjpeg.cv2.imencode", lambda *a, **kw: (False, None))

    mjpeg._process(make_frame(1))

    assert await conn.next_jpeg(timeout=0.05) is None


def test_the_sink_base_class_demands_a_process_implementation():
    """SlotWorkerSink is abstract by convention; forgetting _process must be loud."""
    with pytest.raises(NotImplementedError):
        SlotWorkerSink()._process(make_frame(1))
