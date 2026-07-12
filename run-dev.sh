#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

log() {
  printf '\033[1;36m[dev]\033[0m %s\n' "$*"
}

warn() {
  printf '\033[1;33m[dev]\033[0m %s\n' "$*" >&2
}

die() {
  printf '\033[1;31m[dev]\033[0m %s\n' "$*" >&2
  exit 1
}

find_python() {
  local candidate
  local candidates=()

  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    candidates+=("$VIRTUAL_ENV/bin/python")
  fi

  candidates+=(
    "$ROOT_DIR/.venv/bin/python"
    "$ROOT_DIR/livekit-interview-agent/.venv/bin/python"
  )

  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

[[ -f "$ROOT_DIR/agent.py" ]] || die "Could not find agent.py in $ROOT_DIR"
[[ -f "$FRONTEND_DIR/package.json" ]] || die "Could not find frontend/package.json"
command -v npm >/dev/null 2>&1 || die "npm is not installed or is not on PATH"

PYTHON_BIN="$(find_python)" || die "No project virtual environment was found. Create .venv or activate the existing virtual environment first."

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  warn "Root .env was not found; the Python agent may fail to authenticate."
fi

if [[ ! -f "$FRONTEND_DIR/.env.local" ]]; then
  die "frontend/.env.local was not found. Copy frontend/.env.example and add your credentials first."
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  log "Frontend dependencies are missing; running npm install once..."
  (cd "$FRONTEND_DIR" && npm install)
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  local status=$?
  trap - INT TERM EXIT

  if [[ -n "$BACKEND_PID" ]]; then
    kill -TERM "$BACKEND_PID" 2>/dev/null || true
  fi

  if [[ -n "$FRONTEND_PID" ]]; then
    kill -TERM "$FRONTEND_PID" 2>/dev/null || true
  fi

  if [[ -n "$BACKEND_PID" ]]; then
    wait "$BACKEND_PID" 2>/dev/null || true
  fi

  if [[ -n "$FRONTEND_PID" ]]; then
    wait "$FRONTEND_PID" 2>/dev/null || true
  fi

  log "Backend and frontend stopped."
  exit "$status"
}

trap cleanup INT TERM EXIT

log "Starting LiveKit Python worker..."
(
  cd "$ROOT_DIR"
  exec "$PYTHON_BIN" agent.py dev
) &
BACKEND_PID=$!

log "Starting Next.js frontend..."
(
  cd "$FRONTEND_DIR"
  exec npm run dev
) &
FRONTEND_PID=$!

log "MockMate is starting at http://localhost:3000"
log "Press Ctrl+C once to stop both processes."

set +e
wait -n "$BACKEND_PID" "$FRONTEND_PID"
EXIT_CODE=$?
set -e

if kill -0 "$BACKEND_PID" 2>/dev/null; then
  warn "The frontend stopped, so the backend will also be stopped."
else
  warn "The backend stopped, so the frontend will also be stopped."
fi

exit "$EXIT_CODE"
