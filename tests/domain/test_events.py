import pytest

from app.domain.events import DeviceEvents


async def test_trigger_update_calls_every_async_subscriber():
    seen: list[tuple[str, int]] = []

    async def first(device_id: int) -> None:
        seen.append(("first", device_id))

    async def second(device_id: int) -> None:
        seen.append(("second", device_id))

    DeviceEvents.subscribe_to_update(first)
    DeviceEvents.subscribe_to_update(second)

    await DeviceEvents.trigger_update(7)

    assert seen == [("first", 7), ("second", 7)]


async def test_trigger_update_with_no_subscribers_is_a_noop():
    await DeviceEvents.trigger_update(1)


async def test_subscribers_are_shared_across_the_class():
    calls: list[int] = []

    async def listener(device_id: int) -> None:
        calls.append(device_id)

    DeviceEvents.subscribe_to_update(listener)

    await DeviceEvents.trigger_update(1)
    await DeviceEvents.trigger_update(2)

    assert calls == [1, 2]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "trigger_update awaits every callback, but TelemetryService subscribes a "
        "plain (non-async) classmethod, so dispatching would raise TypeError. "
        "trigger_update has no caller today, which is why it goes unnoticed."
    ),
)
async def test_sync_subscriber_is_dispatched_without_error():
    calls: list[int] = []

    def sync_listener(device_id: int) -> None:
        calls.append(device_id)

    DeviceEvents.subscribe_to_update(sync_listener)

    await DeviceEvents.trigger_update(3)

    assert calls == [3]
