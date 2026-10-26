#!/usr/bin/env bash
# Run the app on this machine against the Supabase database (cloud_demo profile).
#
#   make cloud-run   →   http://localhost:3000
#
# The Docker stack cannot be used for this: its containers sit on an internal-only network with no
# route to the internet, which is what proves the edge profile works offline. So the API and the
# Next.js dev server run directly on the host instead, reading .env.cloud.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="${CLOUD_ENV:-.env.cloud}"
WEB_PORT="${WEB_PORT:-3000}"

# The API's port: API_PORT if given, else 8099 or the next free one (another program, e.g. a Docker
# container, may hold 8099; the web app is told the port, so nothing else needs it).
port_free() { ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
if [ -z "${API_PORT:-}" ]; then
  API_PORT=8099
  while ! port_free "$API_PORT"; do API_PORT=$((API_PORT + 1)); done
  [ "$API_PORT" = 8099 ] || echo "port 8099 is in use: the API takes port $API_PORT"
fi

python3 scripts/check_cloud_env.py "$ENV_FILE" || exit 1

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# The trained detector instead of the simulated one (scripts/run_demo.sh sets this).
if [ -n "${DEMO_MODEL_DIR:-}" ]; then
  export THREADEYE_DETECTOR_PROVIDER=local_model
  export THREADEYE_MODEL_DIR="$DEMO_MODEL_DIR"
fi

# Local overrides: the browser talks plain HTTP here, and Next.js proxies /api to the API,
# so requests stay same-origin.
export THREADEYE_COOKIE_SECURE=false
export THREADEYE_ALLOWED_ORIGINS="http://localhost:${WEB_PORT}"
# Simulated rolls (and the live screen's video) come from data/. Evidence photos are stored in the
# Supabase database itself (table threadeye.blobs), like every other record.
export THREADEYE_DATASETS_DIR="$PWD/data"

VENV_BIN="$PWD/backend/.venv/bin"
[ -x "$VENV_BIN/uvicorn" ] || { echo "backend venv missing: run 'uv sync' in backend/" >&2; exit 1; }

api_pid=""
web_pid=""
cleanup() {
  trap - EXIT INT TERM
  [ -n "$api_pid" ] && kill "$api_pid" 2>/dev/null || true
  [ -n "$web_pid" ] && kill "$web_pid" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "stopped"
}
trap cleanup EXIT INT TERM

echo "starting API on :${API_PORT} (database: Supabase)"
(cd backend && exec "$VENV_BIN/uvicorn" threadeye.api.app:app \
  --host 127.0.0.1 --port "$API_PORT" --log-level warning) &
api_pid=$!

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
health=$(curl -fsS "http://127.0.0.1:${API_PORT}/health" 2>/dev/null || echo '{}')
case "$health" in
  *'"db":"ok"'*) echo "  $health" ;;
  *) echo "API did not become healthy: ${health:-no response}" >&2; exit 1 ;;
esac

echo "starting the web app on :${WEB_PORT}"
(cd frontend && API_ORIGIN="http://127.0.0.1:${API_PORT}" exec pnpm dev --port "$WEB_PORT") &
web_pid=$!

echo
echo "ThreadEye is running against Supabase: http://localhost:${WEB_PORT}"
echo "demo accounts: inspector, supervisor, store, cutting, merchandiser, management, admin"
echo "password: THREADEYE_DEMO_PASSWORD in ${ENV_FILE}"
echo "press Ctrl-C to stop"
wait
