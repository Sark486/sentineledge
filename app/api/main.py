from fastapi import APIRouter

from app.api.v1 import devices, telemetry

api_router = APIRouter()
api_router.include_router(telemetry.router)
api_router.include_router(devices.router)
