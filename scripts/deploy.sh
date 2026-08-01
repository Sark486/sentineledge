#!/usr/bin/env bash
# Idempotent: brings infra up, applies migrations, builds app images.
# Does NOT start the backend/frontend application itself — see start-all.sh.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

command -v docker >/dev/null || { echo "error: docker not found" >&2; exit 1; }
command -v uv     >/dev/null || { echo "error: uv not found" >&2; exit 1; }

echo "==> starting db + mosquitto"
docker compose up -d db mosquitto

echo "==> waiting for db"
for _ in $(seq 1 30); do
  docker compose exec -T db pg_isready -U user -d sentinel >/dev/null 2>&1 && break
  sleep 1
done
docker compose exec -T db pg_isready -U user -d sentinel >/dev/null 2>&1 \
  || { echo "error: db never became ready" >&2; exit 1; }

echo "==> waiting for mosquitto"
for _ in $(seq 1 30); do
  nc -z localhost 1883 2>/dev/null && break
  sleep 1
done
nc -z localhost 1883 2>/dev/null \
  || { echo "error: mosquitto never became ready" >&2; exit 1; }

echo "==> running migrations"
uv run alembic upgrade head

echo "==> building backend + frontend images"
docker compose build backend frontend

echo "==> deploy complete: infra up, migrations applied, images built."
echo "    run ./scripts/start-all.sh to start the application + camera agent."
