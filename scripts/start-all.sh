#!/usr/bin/env bash
# Starts db, mosquitto, backend, frontend (docker) and the camera agent (native).
# Run ./scripts/deploy.sh first if you haven't already.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> starting containers"
docker compose up -d

./scripts/agent-start.sh
