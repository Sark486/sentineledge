from app.domain.sensors import EnvironmentalData
from app.infrastructure.hardware.base import SensorInterface
import asyncio
from aiomqtt import Client
from app.core.deps import get_sensor_adapter # Use your hardware adapter
from app.core.config import settings

DELAY: int = 60

async def sense_hat_publisher():
    adapter: SensorInterface = get_sensor_adapter()
    async with Client(settings.mqtt_host) as client:
        while True:
            data: EnvironmentalData = adapter.read_data()
            data_json: str = data.model_dump_json()
            await client.publish(
                "sentinel/devices/pi_internal/telemetry", 
                payload=data_json
            )
            print("Sense hat publisher: Published data " + data_json)
            await asyncio.sleep(DELAY)
