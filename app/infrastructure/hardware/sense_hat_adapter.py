import random
from .base import SensorInterface
from app.domain.sensors import EnvironmentalData

class MockSenseHat(SensorInterface):
    def read_data(self) -> EnvironmentalData:
        return EnvironmentalData(
            temperature=random.uniform(20.0, 25.0),
            humidity=random.uniform(40.0, 50.0),
            pressure=1013.25,
            source="Mock"
        )

class RealSenseHat(SensorInterface):
    def __init__(self):
        from sense_hat import SenseHat  # Import only if on RPi
        self.sense = SenseHat()

    def read_data(self) -> EnvironmentalData:
        return EnvironmentalData(
            temperature=self.sense.get_temperature(),
            humidity=self.sense.get_humidity(),
            pressure=self.sense.get_pressure(),
            source="Sense HAT"
        )