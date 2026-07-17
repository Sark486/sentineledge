class DeviceEvents:
    _on_update_listeners = []

    @classmethod
    def subscribe_to_update(cls, callback):
        cls._on_update_listeners.append(callback)

    @classmethod
    async def trigger_update(cls, device_id: int):
        for callback in cls._on_update_listeners:
            await callback(device_id)