#!/usr/bin/env bash
# M0 acceptance: the edge stack runs with NO internet access for the app containers.
#   1. every service is up and healthy
#   2. the `internal` network is internal-only (no route out)
#   3. api, worker and web cannot open a connection to the internet
#   4. the app answers through the proxy: /health (DB query), login page, API login
# Usage: scripts/verify_offline.sh   (after `make up`)
set -uo pipefail

PORT="${THREADEYE_HTTP_PORT:-8080}"
BASE="http://localhost:${PORT}"
PROJECT="${COMPOSE_PROJECT_NAME:-threadeye}"
fail=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
bad() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=1; }

echo "1) services healthy"
for svc in db api worker web proxy; do
  cid=$(docker compose -p "$PROJECT" ps -q "$svc" 2>/dev/null)
  if [ -z "$cid" ]; then bad "$svc not running"; continue; fi
  state=$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$cid")
  case "$state" in
    "running healthy"|"running no-healthcheck") pass "$svc ($state)" ;;
    *) bad "$svc ($state)" ;;
  esac
done

echo "2) internal network has no route out"
internal=$(docker network inspect -f '{{.Internal}}' "${PROJECT}_internal" 2>/dev/null)
[ "$internal" = "true" ] && pass "${PROJECT}_internal is internal-only" || bad "${PROJECT}_internal Internal=$internal"

echo "3) app containers cannot reach the internet"
probe_py='import socket,sys
try:
    socket.create_connection(("1.1.1.1", 443), timeout=3); sys.exit(0)
except OSError:
    sys.exit(1)'
for svc in api worker; do
  if docker compose -p "$PROJECT" exec -T "$svc" python -c "$probe_py" >/dev/null 2>&1; then
    bad "$svc CAN reach the internet"
  else
    pass "$svc has no internet access"
  fi
done
probe_js='const s=require("net").connect(443,"1.1.1.1");s.on("connect",()=>process.exit(0));s.on("error",()=>process.exit(1));setTimeout(()=>process.exit(1),3000);'
if docker compose -p "$PROJECT" exec -T web node -e "$probe_js" >/dev/null 2>&1; then
  bad "web CAN reach the internet"
else
  pass "web has no internet access"
fi

echo "4) app works through the proxy"
health=$(curl -fsS "$BASE/health" 2>/dev/null)
if echo "$health" | grep -q '"db":"ok"'; then pass "/health → $health"; else bad "/health → ${health:-no response}"; fi
code=$(curl -s -o /tmp/threadeye_login.html -w '%{http_code}' "$BASE/login")
if [ "$code" = "200" ] && grep -q "ThreadEye" /tmp/threadeye_login.html; then pass "/login page renders (200)"; else bad "/login → $code"; fi
ENV_FILE="${THREADEYE_ENV_FILE:-.env}"
if [ -f "$ENV_FILE" ]; then
  pw=$(grep -E '^THREADEYE_DEMO_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)
  if [ -n "$pw" ]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
      -d "{\"username\":\"inspector\",\"password\":\"${pw}\"}" "$BASE/api/v1/auth/login")
    [ "$code" = "200" ] && pass "API login as demo inspector (200)" || bad "API login → $code"
  fi
fi

echo
if [ "$fail" = "0" ]; then echo "OFFLINE CHECK: PASS"; else echo "OFFLINE CHECK: FAIL"; fi
exit "$fail"
