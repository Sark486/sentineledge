from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.infrastructure.models import DeviceStatus


class PaginatedResponse[T](BaseModel):
    """Generic paginated response wrapper with metadata."""

    count: int
    limit: int
    offset: int
    data: list[T]

    model_config = ConfigDict(arbitrary_types_allowed=True, from_attributes=True)


class LocationBase(BaseModel):
    display_name: str

    model_config = ConfigDict(from_attributes=True)


class DeviceBase(BaseModel):
    display_name: str | None = None


class DeviceUpdate(DeviceBase):
    location_name: str | None = None
    status: DeviceStatus | None = None


class DeviceRead(DeviceBase):
    id: int
    hardware_id: str
    status: DeviceStatus
    location: LocationBase | None = None
    last_seen: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ClimateReadingBase(BaseModel):
    timestamp: datetime
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    location_snapshot: str


class ClimateReadingRead(ClimateReadingBase):
    device_id: int
    device: DeviceRead | None = None

    model_config = ConfigDict(from_attributes=True)


class SeriesPoint(BaseModel):
    timestamp: datetime
    device_id: int
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None

    model_config = ConfigDict(from_attributes=True)


class SeriesResponse(BaseModel):
    interval: str
    requested_interval: str | None = None
    downgraded: bool
    start: datetime
    end: datetime
    data: list[SeriesPoint]


class CurrentReadingRead(BaseModel):
    device_id: int
    display_name: str | None = None
    location: str | None = None
    timestamp: datetime
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None

    model_config = ConfigDict(from_attributes=True)
