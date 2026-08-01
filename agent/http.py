import asyncio
import contextlib
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse

from agent.capture import CaptureController
from agent.config import AgentSettings
from agent.power import PowerManager
from agent.sinks.mjpeg import MJPEGSink, ViewerConnection

BOUNDARY = "frame"


def build_app(
    settings: AgentSettings,
    capture: CaptureController,
    power: PowerManager,
    mjpeg: MJPEGSink,
) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        mjpeg.start()
        power_task = asyncio.create_task(power.run())
        yield
        power_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await power_task
        mjpeg.stop()
        capture.shutdown()

    app = FastAPI(title="sentinel-agent", lifespan=lifespan)

    def check_hardware_id(hardware_id: str) -> None:
        if hardware_id != settings.hardware_id:
            raise HTTPException(status_code=404, detail=f"unknown camera {hardware_id!r}")

    @app.get("/cameras/{hardware_id}/stream")
    async def stream(hardware_id: str) -> StreamingResponse:
        check_hardware_id(hardware_id)
        viewer_id = uuid4().hex
        conn = ViewerConnection()

        async def gen() -> AsyncIterator[bytes]:
            mjpeg.add_viewer(viewer_id, conn)
            power.create_lease(viewer_id)
            try:
                while True:
                    jpeg = await conn.next_jpeg(timeout=settings.lease_ttl_s)
                    if jpeg is None:
                        # A full lease TTL with no frame means the sensor is not
                        # coming back for us — close instead of holding a zombie
                        # connection whose lease has already expired.
                        return
                    yield (
                        f"--{BOUNDARY}\r\n"
                        f"Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(jpeg)}\r\n\r\n"
                    ).encode() + jpeg + b"\r\n"
                    # Only a write the server accepted renews the lease; a dead
                    # client cancels the generator instead of reaching here.
                    power.renew_lease(viewer_id)
            finally:
                mjpeg.remove_viewer(viewer_id)
                power.drop_lease(viewer_id)

        return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}")

    @app.get("/cameras/{hardware_id}/snapshot")
    async def snapshot(hardware_id: str) -> Response:
        check_hardware_id(hardware_id)
        viewer_id = f"snapshot-{uuid4().hex}"
        conn = ViewerConnection()
        mjpeg.add_viewer(viewer_id, conn)
        power.create_lease(viewer_id)
        try:
            # Cold sensor: ≤1s power tick + ~0.4s first frame + AE settle.
            jpeg = await conn.next_jpeg(timeout=3.0 + settings.warmup_s)
        finally:
            mjpeg.remove_viewer(viewer_id)
            power.drop_lease(viewer_id)
        if jpeg is None:
            raise HTTPException(status_code=503, detail="sensor did not deliver a frame")
        return Response(content=jpeg, media_type="image/jpeg")

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "hardware_id": settings.hardware_id,
            "sensor_on": capture.sensor_on,
            "viewers": power.viewer_count,
        }

    return app
