# SentinelEdge

Home environment monitoring system running on a Raspberry Pi. IoT devices publish climate telemetry (temperature, humidity, pressure) over MQTT; a FastAPI backend ingests it into TimescaleDB; a React frontend displays metrics and manages devices.

## Features

- **MQTT telemetry ingestion** — devices publish to `sentinel/devices/<hardware_id>/telemetry`; unknown devices are auto-registered and held in `pending` until approved.
- **Device lifecycle management** — devices move `pending` → `active` / `blocked` from the frontend; telemetry is only persisted for `active` devices.
- **Time-series storage** — TimescaleDB hypertable for raw readings, with `climate_5m` and `climate_1h` continuous aggregates for downsampled queries.
- **Location tracking** — each reading stores a snapshot of the device's location name at write time, so history stays accurate after a device moves.
- **Sense HAT support** — reads the Pi's onboard Sense HAT in `PROD` mode, or a mock sensor for development on any machine.
- **Web dashboard** — metrics charts/tables with filtering, plus device management (React + TypeScript, polling-based updates).

Camera/motion-detection features (Picamera2 + OpenCV vision agent, MJPEG streaming) exist in the codebase but are currently disabled (commented out).

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic |
| Database | TimescaleDB (PostgreSQL), Redis |
| Messaging | Mosquitto MQTT (aiomqtt client) |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, Recharts |
| Tooling | uv, ruff, mypy, pytest |

## Getting started

### Prerequisites

- Docker (for TimescaleDB, Redis, Mosquitto)
- [uv](https://docs.astral.sh/uv/) with Python 3.13
- Node.js 20+ (for the frontend)

### 1. Start infrastructure

```bash
docker compose up -d
```

This starts TimescaleDB on `5432`, Redis on `6379`, and Mosquitto on `1883`.

### 2. Configure the backend

Create `.env` in the repo root:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sentinel
REDIS_URL=redis://localhost:6379/0
MQTT_HOST=localhost
HARDWARE_MODE=MOCK   # PROD = real Sense HAT (Raspberry Pi only)
```

### 3. Run migrations and start the backend

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify with `http://localhost:8000/health`. Interactive API docs are at `http://localhost:8000/docs`.

### 4. Start the frontend

```bash
cd frontend
npm install
cp .env.example .env   # points VITE_API_BASE_URL at http://localhost:8000/api/v1
npm run dev
```

Open `http://localhost:5173`. See [frontend/README.md](frontend/README.md) for details and troubleshooting.

## Sending telemetry

Devices publish JSON to `sentinel/devices/<hardware_id>/telemetry`:

```bash
mosquitto_pub -h localhost -t "sentinel/devices/my-sensor-01/telemetry" \
  -m '{"temperature": 21.4, "humidity": 45.2, "pressure": 1013.25}'
```

First publish auto-registers the device with status `pending`. Approve it on the dashboard's Devices tab (or `PATCH /api/v1/devices/{id}` with `{"status": "active"}`) — only then are its readings stored.

## API overview

All endpoints are under `/api/v1`:

- `GET /telemetry` — climate readings with filters (`device_id`, `location`, `start_date`, `end_date`) and pagination
- `GET /telemetry/current` — live reading from the local sensor
- `GET /devices/` — list devices; `PATCH /devices/{id}` — update name/location/status
- `GET /devices/{id}/latest` — latest reading for a device

## Development

```bash
uv run ruff check app    # lint
uv run mypy app          # type check
uv run pytest            # tests

cd frontend
npm run lint             # eslint
npm run typecheck        # tsc --noEmit
npm run build            # production build
```

Creating a migration:

```bash
uv run alembic revision --autogenerate -m "message"
```

Note: Alembic autogenerate cannot emit TimescaleDB DDL (hypertables, continuous aggregates) — add those as raw `op.execute()` statements by hand. See `migrations/versions/98e6c996836c_*.py` for the pattern.

Architecture notes for working in this codebase live in [CLAUDE.md](CLAUDE.md).
