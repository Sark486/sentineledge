from abc import ABC, abstractmethod
from app.domain.sensors import EnvironmentalData

class SensorInterface(ABC):
    @abstractmethod
    def read_data(self) -> EnvironmentalData:
        pass