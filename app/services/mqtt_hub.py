import asyncio
import json
import logging
from typing import Any

import aiomqtt
from pydantic import ValidationError

from app.core.service_factories import create_device_service, create_telemetry_service
from app.domain.sensors import EnvironmentalData
from app.infrastructure.db import async_session_maker
from app.infrastructure.models import Device, DeviceStatus

logger = logging.getLogger(__name__)

RECONNECT_DELAY_S = 5


class MQTTHub:
    def __init__(self, broker_host: str = "localhost"):
        self.broker_host = broker_host
        self.topic_filter = "sentinel/devices/+/telemetry"

    async def start(self) -> None:
        while True:
            try:
                async with aiomqtt.Client(self.broker_host, clean_session=True) as client:
                    await client.subscribe(self.topic_filter)
                    async for message in client.messages:
                        try:
                            await self._handle_message(message)
                        except Exception:
                            logger.exception("Unhandled error handling %s", message.topic)
            except aiomqtt.MqttError as e:
                logger.warning("Connection error (%s), retrying in %ss", e, RECONNECT_DELAY_S)
                await asyncio.sleep(RECONNECT_DELAY_S)

    async def _handle_message(self, message: aiomqtt.Message) -> None:
        topic_parts = str(message.topic).split("/")
        if len(topic_parts) < 3:
            logger.warning("Ignoring message on unexpected topic %s", message.topic)
            return
        hardware_id = topic_parts[2]

        try:
            payload: Any = json.loads(message.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("Undecodable payload on %s: %s", message.topic, e)
            return

        if not isinstance(payload, dict):
            logger.warning("Ignoring non-object payload on %s", message.topic)
            return

        payload.pop("source", None)

        try:
            climate_data = EnvironmentalData(source=hardware_id, **payload)
        except ValidationError as e:
            logger.warning("Invalid climate data from %s: %s", hardware_id, e)
            return

        async with async_session_maker() as session:
            try:
                telemetry_service = create_telemetry_service(session)
                device_service = create_device_service(session)

                device: Device = await device_service.get_or_create_device(hardware_id)

                if device.status == DeviceStatus.ACTIVE:
                    await telemetry_service.save_telemetry(device.id, climate_data)
                    await device_service.mark_online(device.id)
                else:
                    logger.debug("Dropping reading from %s device %s", device.status, hardware_id)

                await session.commit()
            except Exception:
                logger.exception("Failed to ingest reading from %s", hardware_id)
                await session.rollback()
