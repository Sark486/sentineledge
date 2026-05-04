from app.core.config import settings
from app.infrastructure.hardware.sense_hat_adapter import MockSenseHat, RealSenseHat
from app.infrastructure.hardware.base import SensorInterface

def get_sensor_adapter() -> SensorInterface:
    if settings.hardware_mode == "PROD":
        return RealSenseHat()
    return MockSenseHat()
