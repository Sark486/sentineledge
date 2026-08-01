from fastapi.applications import FastAPI
import logging

import uvicorn

from agent.capture import CaptureController, FrameBus
from agent.config import AgentSettings
from agent.http import build_app
from agent.power import PowerManager
from agent.sinks.mjpeg import MJPEGSink


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = AgentSettings()
    bus = FrameBus()
    capture = CaptureController(bus)
    power = PowerManager(settings, capture)
    mjpeg = MJPEGSink(settings)
    bus.register(mjpeg)
    app: FastAPI = build_app(settings, capture, power, mjpeg)
    uvicorn.run(app, host="0.0.0.0", port=settings.http_port, log_level="info")


if __name__ == "__main__":
    main()
