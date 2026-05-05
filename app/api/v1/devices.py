from app.core.deps import get_device_service, get_telemetry_service
from typing import Any
from fastapi import APIRouter, Depends
from app.services.device_service import DeviceService
from app.services.telemetry_service import TelemetryService
from app.exceptions.sentinet_not_found_error import SentinelNotFoundError
from app.api.schemas import DeviceRead, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["Devices"])

@router.get("/", response_model=list[DeviceRead])
async def list_devices(service: DeviceService = Depends(get_device_service)) -> Any:
    return await service.list_devices()

@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(device_id: int, service: DeviceService = Depends(get_device_service)) -> Any:
    device = await service.get_device_by_id(device_id)
    if not device:
        raise SentinelNotFoundError
    return device

@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int, 
    update_data: DeviceUpdate,
    service: DeviceService = Depends(get_device_service)
) -> Any:
    device = await service.update_device(device_id, update_data)
    
    if not device:
        raise SentinelNotFoundError
        
    return device

@router.get("/{device_id}/latest")
async def get_latest_telemetry_data(device_id: int, service: TelemetryService = Depends(get_telemetry_service)):
    latest = await service.get_latest_telemetry_by_device(device_id)
    
    if not latest:
        raise SentinelNotFoundError
    
    return latest