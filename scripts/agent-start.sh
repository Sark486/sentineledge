#!/usr/bin/env bash
# Starts the camera agent as a detached background process that keeps running
# after the terminal closes. The agent can't run in Docker (needs /dev/video*
# and the Pi's picamera2/libcamera via --system-site-packages).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PIDFILE=scripts/agent.pid
LOG=scripts/logs/agent.log

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "agent already running (pid $(cat "$PIDFILE"))"
  exit 0
fi

if [[ ! -x agent/.venv/bin/python ]]; then
  cat >&2 <<'EOF'
error: agent/.venv is not set up (agent/.venv/bin/python missing).

Set it up once with:
  uv venv --python /usr/bin/python3 --system-site-packages agent/.venv
  uv pip install --python agent/.venv/bin/python -e agent
EOF
  exit 1
fi

mkdir -p scripts/logs
setsid agent/.venv/bin/python -m agent >>"$LOG" 2>&1 < /dev/null &
echo $! > "$PIDFILE"
disown
echo "agent started (pid $(cat "$PIDFILE")), logging to $LOG"
