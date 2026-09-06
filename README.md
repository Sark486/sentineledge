# SentinelEdge

Home environment monitoring system running on a Raspberry Pi. IoT devices publish climate telemetry (temperature, humidity, pressure) over MQTT; a FastAPI backend ingests it into TimescaleDB; a React frontend displays metrics and manages devices.

<img src="docs/images/dashboard.png" alt="SentinelEdge dashboard" width="400">

## System overview

SentinelEdge is a home environment monitoring system in two parts:

- **sentineledge** (this repo) - Raspberry Pi gateway. FastAPI backend ingesting MQTT
  telemetry into TimescaleDB, a React dashboard, and a camera agent.
- **[sentineledge-firmware](https://github.com/Sark486/sentineledge-firmware)** -
  ESP32-C3 sensor nodes in C++. AHT20 and BMP280 over I2C, publishing JSON once a minute.

Nodes publish to `sentinel/devices/<hardware_id>/telemetry`; this repo ingests, stores and
serves that data.

## Features

- **MQTT telemetry ingestion** - devices publish to `sentinel/devices/<hardware_id>/telemetry`; unknown devices are auto-registered and held in `pending` until approved.
- **Device identity from the topic** - the hardware id is always taken from the MQTT topic and any `source` field in the payload is ignored, so one device cannot publish telemetry as another.
- **Device lifecycle management** - devices move `pending` → `active` / `blocked` from the frontend; telemetry is only persisted for `active` devices.
- **Time-series storage** - TimescaleDB hypertable for raw readings, with `climate_5m` and `climate_1h` continuous aggregates for downsampled queries.
- **Location tracking** - each reading stores a snapshot of the device's location name at write time, so history stays accurate after a device moves.
- **Camera agent** - a separate process (`agent/`) that owns the Pi camera and serves MJPEG streams and snapshots, powering the sensor only while someone is watching.
- **Web dashboard** - metrics charts/tables with filtering, plus device management (React + TypeScript, polling-based updates).

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic |
| Database | TimescaleDB (PostgreSQL) |
| Messaging | Mosquitto MQTT (aiomqtt client) |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, Recharts |
| Camera agent | Picamera2, OpenCV, FastAPI (its own project under `agent/`) |
| Tooling | uv, ruff, mypy, pytest |

## Design notes

**TimescaleDB with continuous aggregates rather than plain Postgres.** Raw readings land in
a `climate_readings` hypertable; `climate_5m` and `climate_1h` are continuous aggregates
kept current by refresh policies, and retention policies drop raw rows after 7 days and
5-minute rollups after 30, leaving hourly history indefinitely - rollups, refresh schedule
and retention are all declarative Timescale policies rather than hand-rolled jobs (see
`migrations/versions/98e6c996836c_*.py`). `/telemetry/series` reads from that ladder:
`resolve_interval` coarsens the requested (or range-derived) interval to the finest one
retention can still serve for the range, and reports `downgraded: true` when it had to
(`app/domain/intervals.py`). Both aggregates run with `materialized_only = false` so a
chart ending at "now" still gets the buckets the refresh policy has not materialised yet.

**The `pending` → `active` / `blocked` device lifecycle.** The MQTT hub takes the hardware
id from the topic and calls `get_or_create_device`, so a device it has never heard of is
registered on its first publish with status `pending` - that registration is what makes it
appear on the Devices page for an operator to approve. Until it is `active` its readings
are dropped and its `last_seen` is left untouched; a `blocked` device stays registered, so
it is not re-created by the next message it sends. The broker accepts anonymous publishes
(`mosquitto/config/mosquitto.conf`), so this status gate is the only thing standing between
an arbitrary publisher on the network and the readings table.

**Location snapshotting at write time.** Every `climate_readings` row carries a
`location_snapshot` string, read from the device's current location on each write
(`TelemetryService.save_telemetry`) instead of being resolved by joining `devices` →
`locations` at read time. The continuous aggregates group by that column and the
`?location=` filters compare against it, so history stays filed under the location a
reading was actually taken in after the device moves. The trade-off is that the name is
frozen per row: moving a device or renaming a location splits its history across two names,
and there is no path to re-attribute the old rows. `/telemetry/latest` is the exception -
it joins the device's current `Location`, so it reports where a device is now.

**The camera agent as a separate host process with a viewer lease.** `CaptureController`
owns the sensor on one long-lived thread because Picamera2 open/close and `capture_arrays()`
block; the asyncio side only flips `set_desired()`. Power is decided from leases rather
than a viewer refcount: a lease is renewed only by a frame the server successfully wrote to
that viewer's socket, so a dead viewer stops renewing and ages out after `lease_ttl_s`
(5s) - as `PowerManager` puts it, no code path can leak a viewer. Creating a lease counts
as a write, since the sensor must come up before any real frame can renew it, and when the
last lease dies the sensor is held for `power_off_grace_s` (10s) so a page refresh does not
power-cycle it. Snapshots take the same kind of lease under a `snapshot-` id and always
drop it in a `finally`.

## Quick start (on the Raspberry Pi)

Running the full system on the target device. Start here.

First-time setup (or after pulling changes that touch dependencies/migrations):

```bash
./scripts/deploy.sh
```

This starts the database and MQTT broker, applies migrations, and builds the backend/frontend
images. It does not start the application itself, so it's safe to re-run any time - it's
idempotent.

Then, day to day:

```bash
./scripts/start-all.sh   # starts db, mosquitto, backend, frontend, and the camera agent
./scripts/stop-all.sh    # stops all of the above
```

The camera agent runs natively on the host (it needs the Pi's camera and can't run in a
container) and keeps running after you close the terminal. To control it on its own:

```bash
./scripts/agent-start.sh
./scripts/agent-stop.sh
```

Agent output is logged to `scripts/logs/agent.log`.

See "Development setup" below to run pieces individually, e.g. with the backend/frontend on
the host instead of in containers.

## Development setup (on your own machine)

Running individual components on a host machine for development.

### Prerequisites

- Docker (for TimescaleDB and Mosquitto)
- [uv](https://docs.astral.sh/uv/) with Python 3.13
- Node.js 20+ (for the frontend)

### 1. Start infrastructure

```bash
docker compose up -d db mosquitto
```

This starts TimescaleDB on `5432` and Mosquitto on `1883`. A bare `docker compose up -d`
also builds and runs the `backend` and `frontend` services in containers, which point at
`db:5432` rather than `localhost` - use that only if you don't want to run the backend on
the host.

### 2. Configure the backend

```bash
cp .env.example .env
```

The defaults match the compose services when the backend runs on the host:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sentinel
MQTT_HOST=localhost
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

Sensor nodes are ESP32-C3 devices running
[sentineledge-firmware](https://github.com/Sark486/sentineledge-firmware). The
`mosquitto_pub` command below is for testing the ingestion path without hardware.

Devices publish JSON to `sentinel/devices/<hardware_id>/telemetry`:

```bash
mosquitto_pub -h localhost -t "sentinel/devices/my-sensor-01/telemetry" \
  -m '{"temperature": 21.4, "humidity": 45.2, "pressure": 1013.25}'
```

First publish auto-registers the device with status `pending`. Approve it on the dashboard's Devices tab (or `PATCH /api/v1/devices/{id}` with `{"status": "active"}`) - only then are its readings stored.

A `source` field in the payload is ignored: the hardware id always comes from the topic, so one device cannot publish as another.

## API overview

All endpoints are under `/api/v1`:

| Endpoint | Purpose |
|---|---|
| `GET /telemetry` | Climate readings with filters (`device_id`, `location`, `start_date`, `end_date`) and pagination |
| `GET /telemetry/series` | Pre-aggregated time series bucketed at `1m`/`5m`/`1h`; the interval is coarsened automatically when retention no longer covers the range |
| `GET /telemetry/latest` | Latest stored reading per device that reported within the online window |
| `GET /telemetry/by-device/{id}` | As `GET /telemetry`, with the device fixed by the path |
| `GET /telemetry/by-location/{name}` | As `GET /telemetry`, with the location fixed by the path |
| `GET /devices` | List devices |
| `GET /devices/{id}` | One device |
| `PATCH /devices/{id}` | Update name, location and/or status - every field is optional |
| `GET /devices/{id}/latest` | Latest reading for a device; empty for a device that has never reported |

## Camera agent

`agent/` is a standalone process that runs **on the Pi host**, not in Docker - the backend
container has no access to `/dev/video*`. It owns the camera exclusively and exposes MJPEG
streaming, snapshots and `/health` on port 8090. The sensor is powered only while a viewer
holds a live lease, with a grace period so a page refresh doesn't power-cycle it.

It has its own `pyproject.toml` and needs a venv with system site packages to reach
Debian's `picamera2`/`libcamera`:

```bash
uv venv --python /usr/bin/python3 --system-site-packages agent/.venv
uv pip install --python agent/.venv/bin/python -e agent
agent/.venv/bin/python -m agent
```

Never `uv sync` inside `agent/`: it can recreate the venv and drop `--system-site-packages`.

## Tests

```bash
uv run pytest                                                    # all tests
uv run pytest --cov=app --cov=agent --cov-report=term-missing    # with coverage
uv run pytest tests/services                                     # one directory
```

No database, MQTT broker or camera required.

## Development

```bash
uv run ruff check .      # lint
uv run mypy app          # type check

cd frontend
npm run lint             # eslint
npm run typecheck        # tsc --noEmit
npm run build            # production build
```

Creating a migration:

```bash
uv run alembic revision --autogenerate -m "message"
```

Note: Alembic autogenerate cannot emit TimescaleDB DDL (hypertables, continuous aggregates) - add those as raw `op.execute()` statements by hand. See `migrations/versions/98e6c996836c_*.py` for the pattern.
