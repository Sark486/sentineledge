from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
# import redis
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.api.main import api_router
from app.services.mqtt_hub import MQTTHub
# from app.services.sense_hat_worker import sense_hat_publisher
from app.exceptions.sentinet_not_found_error import SentinelNotFoundError
# from app.services.workers.vision_agent import VisionAgent

mqtt_manager = MQTTHub(broker_host=settings.mqtt_host)

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    hub_task = loop.create_task(mqtt_manager.start())
    # local_sensor_task = loop.create_task(sense_hat_publisher())

    # r = redis.Redis(host='localhost', decode_responses=True)

    # agent = VisionAgent(redis_client=r)
    # agent.start()
    # app.state.vision_agent = agent
    
    print("SentinelEdge Services Started: MQTT Hub and Local Sense Hat Worker")
    
    yield
    
    print("Shutting down services...")
    hub_task.cancel()
    # local_sensor_task.cancel()

    # if hasattr(app.state, "vision_agent"):
    #     app.state.vision_agent.stop()
    
    await asyncio.gather(hub_task, return_exceptions=True)
    print("All background tasks stopped.")

app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.exception_handler(SentinelNotFoundError)
async def sentinel_not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})