from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime

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