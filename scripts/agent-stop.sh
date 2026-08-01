#!/usr/bin/env bash
# Stops the camera agent started by agent-start.sh.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PIDFILE=scripts/agent.pid

if [[ ! -f "$PIDFILE" ]] || ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "agent not running"
  rm -f "$PIDFILE"
  exit 0
fi

kill -TERM "$(cat "$PIDFILE")"
rm -f "$PIDFILE"
echo "agent stopped"
