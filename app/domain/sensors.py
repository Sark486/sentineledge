from pydantic import BaseModel, Field
from datetime import datetime, timezone

class EnvironmentalData(BaseModel):
    temperature: float
    humidity: float
    pressure: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
