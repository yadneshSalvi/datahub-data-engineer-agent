#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_URL="http://localhost:8001"
FRONTEND_URL="http://localhost:3001"
BACKEND_PID=""
FRONTEND_PID=""

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

GMS_URL="${DATAHUB_GMS_URL:-http://localhost:8081}"
GMS_URL="${GMS_URL%/}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/uv-cache}"

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  [[ -n "$FRONTEND_PID" ]] && wait "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$BACKEND_PID" ]] && wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'error: required command not found: %s\n' "$1" >&2
    exit 1
  fi
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local pid="${3:-}"
  local attempt
  for attempt in {1..60}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      printf 'error: %s exited before becoming ready\n' "$name" >&2
      return 1
    fi
    sleep 1
  done
  printf 'error: timed out waiting for %s at %s\n' "$name" "$url" >&2
  return 1
}

printf '==> Checking prerequisites\n'
require_command curl
require_command docker
require_command uv
if ! command -v bun >/dev/null 2>&1 && ! command -v npm >/dev/null 2>&1; then
  printf 'error: install bun or npm to run the frontend\n' >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  printf 'error: Docker is not running; start Docker and the DataHub quickstart first\n' >&2
  exit 1
fi
if ! curl -fsS --max-time 3 "$GMS_URL/health" >/dev/null 2>&1; then
  printf 'error: DataHub GMS is not reachable at %s\n' "$GMS_URL" >&2
  printf '       Start your DataHub quickstart or set DATAHUB_GMS_URL in .env.\n' >&2
  exit 1
fi

printf '==> Installing backend dependencies\n'
(
  cd "$BACKEND_DIR"
  env -u VIRTUAL_ENV uv sync
)

printf '==> Installing frontend dependencies\n'
if command -v bun >/dev/null 2>&1; then
  (
    cd "$FRONTEND_DIR"
    bun install --frozen-lockfile
  )
else
  (
    cd "$FRONTEND_DIR"
    npm install
  )
fi

if curl -fsS "$BACKEND_URL/api/health" >/dev/null 2>&1; then
  printf '==> Reusing backend already running at %s\n' "$BACKEND_URL"
else
  printf '==> Starting backend\n'
  (
    cd "$BACKEND_DIR"
    exec env -u VIRTUAL_ENV uv run uvicorn oncall_agent.app:app --host 0.0.0.0 --port 8001
  ) &
  BACKEND_PID=$!
fi
wait_for_url "backend" "$BACKEND_URL/api/health" "$BACKEND_PID"

DEMO_STATE="$(curl -fsS "$BACKEND_URL/api/demo/state")"
if [[ "$DEMO_STATE" != *'"seeded":true'* ]]; then
  printf '==> Demo catalog is unseeded; seeding and verifying it now\n'
  (
    cd "$BACKEND_DIR"
    env -u VIRTUAL_ENV uv run python -m demo.seed --verify
  )
else
  printf '==> Demo catalog is already seeded\n'
fi

if curl -fsS "$FRONTEND_URL" >/dev/null 2>&1; then
  printf '==> Reusing frontend already running at %s\n' "$FRONTEND_URL"
else
  printf '==> Starting frontend\n'
  if command -v bun >/dev/null 2>&1; then
    (
      cd "$FRONTEND_DIR"
      exec bun run dev --host 0.0.0.0
    ) &
  else
    (
      cd "$FRONTEND_DIR"
      exec npm run dev -- --host 0.0.0.0
    ) &
  fi
  FRONTEND_PID=$!
fi
wait_for_url "frontend" "$FRONTEND_URL" "$FRONTEND_PID"

printf '\nReady:\n'
printf '  App:      %s\n' "$FRONTEND_URL"
printf '  API:      %s\n' "$BACKEND_URL"
printf '  DataHub:  %s\n' "${DATAHUB_UI_URL:-http://localhost:9002}"
printf '  GMS:      %s\n' "$GMS_URL"
printf '\nPress Ctrl-C to stop services started by this script.\n'

if [[ -n "$BACKEND_PID" || -n "$FRONTEND_PID" ]]; then
  wait
else
  printf 'Both app services were already running; nothing to supervise.\n'
fi
