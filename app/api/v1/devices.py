from fastapi import APIRouter

from app.api.schemas import ClimateReadingRead, DeviceRead, DeviceUpdate, PaginatedResponse
from app.core.deps import DeviceServiceDep, TelemetryServiceDep
from app.domain.exceptions import SentinelNotFoundError

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=PaginatedResponse[DeviceRead])
async def list_devices(service: DeviceServiceDep) -> PaginatedResponse:
    devices = list(await service.list_devices())
    return PaginatedResponse(
        count=len(devices),
        limit=len(devices),
        offset=0,
        data=devices,
    )


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(device_id: int, service: DeviceServiceDep) -> DeviceRead:
    device = await service.get_device_by_id(device_id)
    if not device:
        raise SentinelNotFoundError(f"Device {device_id} not found")
    return DeviceRead.model_validate(device)


@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int,
    update_data: DeviceUpdate,
    service: DeviceServiceDep,
) -> DeviceRead:
    device = await service.update_device(device_id, update_data)
    if not device:
        raise SentinelNotFoundError(f"Device {device_id} not found")
    return DeviceRead.model_validate(device)


@router.get("/{device_id}/latest", response_model=list[ClimateReadingRead])
async def get_latest_telemetry_data(
    device_id: int,
    device_service: DeviceServiceDep,
    telemetry_service: TelemetryServiceDep,
) -> list[ClimateReadingRead]:
    """Latest reading for a device.

    Empty for a device that has never reported - only an unknown device is a 404,
    so the two cases stay distinguishable.
    """
    if not await device_service.get_device_by_id(device_id):
        raise SentinelNotFoundError(f"Device {device_id} not found")

    readings = await telemetry_service.get_latest_telemetry_by_device(device_id)
    return [ClimateReadingRead.model_validate(reading) for reading in readings]
