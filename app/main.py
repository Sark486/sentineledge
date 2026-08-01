import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.main import api_router
from app.core.config import settings
from app.domain.exceptions import SentinelNotFoundError
from app.services.mqtt_hub import MQTTHub

logger = logging.getLogger(__name__)

mqtt_manager = MQTTHub(broker_host=settings.mqtt_host)


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub_task = asyncio.create_task(mqtt_manager.start())
    logger.info("SentinelEdge services started: MQTT hub")

    yield

    logger.info("Shutting down services...")
    hub_task.cancel()
    await asyncio.gather(hub_task, return_exceptions=True)
    logger.info("All background tasks stopped.")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_v1_str)


@app.exception_handler(SentinelNotFoundError)
async def sentinel_not_found_handler(request: Request, exc: SentinelNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc) or "Resource not found"})
