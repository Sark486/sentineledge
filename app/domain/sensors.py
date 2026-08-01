from datetime import UTC, datetime

from pydantic import BaseModel, Field


class EnvironmentalData(BaseModel):
    temperature: float
    humidity: float
    pressure: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str
