from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel, ConfigDict
from datetime import datetime

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper with metadata."""
    count: int
    limit: int
    offset: int
    data: List[T]

    model_config = ConfigDict(arbitrary_types_allowed=True)

class LocationBase(BaseModel):
    display_name: str

    class Config:
        from_attributes = True

class LocationRead(LocationBase):
    id: int

class DeviceBase(BaseModel):
    display_name: Optional[str] | None = None
    location: Optional[LocationBase] = None
    status: Optional[str] | None = None

class DeviceCreate(DeviceBase):
    hardware_id: str

class DeviceUpdate(DeviceBase):
    location_name: str

class DeviceRead(DeviceBase):
    id: int
    hardware_id: str
    status: str
    last_seen: datetime | None

    model_config = ConfigDict(from_attributes=True)

class ClimateReadingBase(BaseModel):
    timestamp: datetime
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    location_snapshot: str

class ClimateReadingRead(ClimateReadingBase):
    device_id: int
    device: Optional[DeviceRead] = None

    model_config = ConfigDict(from_attributes=True)

class SeriesPoint(BaseModel):
    timestamp: datetime
    device_id: int
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

class SeriesResponse(BaseModel):
    interval: str
    requested_interval: Optional[str] = None
    downgraded: bool
    start: datetime
    end: datetime
    data: List[SeriesPoint]

class CurrentReadingRead(BaseModel):
    device_id: int
    display_name: Optional[str] = None
    location: Optional[str] = None
    timestamp: datetime
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)