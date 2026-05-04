from typing import Any
import json
import asyncio
from datetime import datetime, timezone
import aiomqtt
from app.infrastructure.db import async_session_maker
from app.infrastructure.repositories import DeviceRepository
from app.infrastructure.models import DeviceStatus, Device

class MQTTHub:
    def __init__(self, broker_host: str = "localhost"):
        self.broker_host = broker_host
        self.topic_filter = "sentinel/devices/+/telemetry"

    async def start(self):
        while True:
            try:
                async with aiomqtt.Client(self.broker_host) as client:
                    await client.subscribe(self.topic_filter)
                    async for message in client.messages:
                        await self._handle_message(message)
            except aiomqtt.MqttError:
                await asyncio.sleep(5)

    async def _handle_message(self, message: aiomqtt.Message):
        topic_parts = str(message.topic).split("/")
        hardware_id = topic_parts[2]

        try:
            payload: Any = json.loads(message.payload.decode())
            print(f"MQTT Listener: received message {payload}")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"MQTT Listener: ERROR {e}")
            return

        async with async_session_maker() as session:
            try:
                print("MQTT Listener: storing to DB ")
                repo = DeviceRepository(session)
                
                device: Device = await repo.get_or_create_device(hardware_id)
                
                if device.status == DeviceStatus.ACTIVE:
                    await repo.add_telemetry(device.id, payload)
                    
                    device.is_online = True
                    device.last_seen = datetime.now(timezone.utc)
                
                await session.commit()
            except Exception as e:
                print(f"!!! MQTT HANDLER CRASHED !!! Error: {e}")
