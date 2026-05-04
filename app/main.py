from fastapi.responses import JSONResponse
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.api.main import api_router
from app.services.mqtt_hub import MQTTHub
from app.services.sense_hat_worker import sense_hat_publisher
from app.exceptions.sentinet_not_found_error import SentinelNotFoundError

mqtt_manager = MQTTHub()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the startup and shutdown of background tasks.
    """
    loop = asyncio.get_event_loop()
    # 1. STARTUP: Launch background workers
    # Task A: The Hub (Listener) - Listens to MQTT and saves to DB
    hub_task = loop.create_task(mqtt_manager.start())
    
    # Task B: The Local Client (Publisher) - Reads Sense Hat and sends to MQTT
    local_sensor_task = loop.create_task(sense_hat_publisher())
    
    print("🚀 SentinelEdge Services Started: MQTT Hub and Local Sense Hat Worker")
    
    yield
    
    # 2. SHUTDOWN: Cleanly cancel tasks
    print("🛑 Shutting down services...")
    hub_task.cancel()
    local_sensor_task.cancel()
    
    # Wait for tasks to acknowledge cancellation
    await asyncio.gather(hub_task, local_sensor_task, return_exceptions=True)
    print("✅ All background tasks stopped.")

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.exception_handler(SentinelNotFoundError)
async def sentinel_not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})