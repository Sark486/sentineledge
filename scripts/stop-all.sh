#!/usr/bin/env bash
# Stops all containers and the camera agent started by start-all.sh.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> stopping containers"
docker compose stop

./scripts/agent-stop.sh
