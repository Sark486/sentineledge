from app.infrastructure.service_factories import create_telemetry_service, create_device_service
from typing import Any
import json
import asyncio
import aiomqtt
from app.infrastructure.db import async_session_maker
from app.infrastructure.models import DeviceStatus, Device
from app.services.telemetry_service import TelemetryService
from app.services.device_service import DeviceService

class MQTTHub:
    def __init__(self, broker_host: str = "localhost"):
        self.broker_host = broker_host
        self.topic_filter = "sentinel/devices/+/telemetry"

    async def start(self):
        while True:
            try:
                async with aiomqtt.Client(self.broker_host, clean_session=True) as client:
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
            print(f"MQTT Listener: received message {payload} on topic {message.topic}")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"MQTT Listener: ERROR {e}")
            return

        async with async_session_maker() as session:
            try:
                print("MQTT Listener: storing to DB ")
                telemetry_service: TelemetryService = create_telemetry_service(session)
                device_service: DeviceService = create_device_service(session)

                device: Device = await device_service.get_or_create_device(hardware_id)
                
                if device.status == DeviceStatus.ACTIVE:
                    await telemetry_service.save_telemetry(device.id, payload)
                    await device_service.mark_online(device.id)
                
                await session.commit()
            except Exception as e:
                print(f"!!! MQTT HANDLER CRASHED !!! Error: {e}")
