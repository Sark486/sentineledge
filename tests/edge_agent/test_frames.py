"""LatestSlot is the hand-off between the blocking capture thread and each
sink's worker thread. Its whole job is to drop stale frames rather than queue
or block, so these tests hammer that contract from both sides."""

import threading
import time

import numpy as np
import pytest

from agent.frames import Frame, LatestSlot


def make_frame(seq: int = 0) -> Frame:
    return Frame(
        seq=seq,
        ts=time.time(),
        main=np.zeros((480, 640, 3), dtype=np.uint8),
        lores_y=np.zeros((240, 320), dtype=np.uint8),
    )


def test_get_returns_the_frame_that_was_put():
    slot = LatestSlot()
    frame = make_frame(1)

    slot.put(frame)

    assert slot.get(timeout=0.1) is frame


def test_get_on_an_empty_slot_times_out_to_none():
    slot = LatestSlot()

    started = time.monotonic()
    assert slot.get(timeout=0.05) is None
    assert time.monotonic() - started >= 0.04


def test_a_frame_is_consumed_only_once():
    slot = LatestSlot()
    slot.put(make_frame(1))

    assert slot.get(timeout=0.1) is not None
    assert slot.get(timeout=0.01) is None


def test_a_slow_reader_only_ever_sees_the_newest_frame():
    """Drop-oldest: queuing instead would either grow without bound or stall the
    capture thread, and stale frames are worth less than either."""
    slot = LatestSlot()
    for seq in range(5):
        slot.put(make_frame(seq))

    frame = slot.get(timeout=0.1)

    assert frame is not None
    assert frame.seq == 4
    assert slot.get(timeout=0.01) is None


def test_a_waiting_reader_is_woken_by_a_put():
    slot = LatestSlot()
    received = []

    def reader():
        received.append(slot.get(timeout=2.0))

    thread = threading.Thread(target=reader)
    thread.start()
    time.sleep(0.05)  # let the reader block on the condition
    frame = make_frame(9)
    slot.put(frame)
    thread.join(timeout=2.0)

    assert received == [frame]


def test_frame_carries_both_resolutions():
    frame = make_frame(1)

    assert frame.main.shape == (480, 640, 3)
    assert frame.lores_y.shape == (240, 320)


def test_frame_is_slotted_and_rejects_stray_attributes():
    """`slots=True` keeps per-frame overhead down on the Pi."""
    frame = make_frame(1)

    with pytest.raises(AttributeError):
        setattr(frame, "something_else", 1)
