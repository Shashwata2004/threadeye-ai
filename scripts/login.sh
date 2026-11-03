#!/usr/bin/env bash
# Log in as a demo role and print the session cookie + the account's permissions.
#
#   ./scripts/login.sh inspector            # log in as the inspector
#   ./scripts/login.sh admin --permissions  # also list every permission
#
# Uses the password from .env.cloud (THREADEYE_DEMO_PASSWORD) against the API that
# scripts/run_cloud.sh starts on :8099. Override the API with API=... if needed.
set -euo pipefail

cd "$(dirname "$0")/.."

USER_NAME="${1:-inspector}"
ENV_FILE="${CLOUD_ENV:-.env.cloud}"
API="${API:-http://127.0.0.1:8099}/api/v1"

[ -f "$ENV_FILE" ] || { echo "$ENV_FILE is missing (it holds THREADEYE_DEMO_PASSWORD)" >&2; exit 1; }
PASSWORD="$(grep -E '^THREADEYE_DEMO_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"
[ -n "$PASSWORD" ] || { echo "THREADEYE_DEMO_PASSWORD not set in $ENV_FILE" >&2; exit 1; }

curl -fsS -c /tmp/threadeye_cookies.txt \
  -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USER_NAME\",\"password\":\"$PASSWORD\"}" \
  -o /tmp/threadeye_me.json

python3 - "$USER_NAME" <<'PY'
import json, sys

me = json.load(open("/tmp/threadeye_me.json"))
print(f"logged in as {me['username']}  ({me['display_name']})")
print(f"  role   : {me['role']}")
print(f"  locale : {me['locale']}")
perms = me.get("permissions", [])
print(f"  perms  : {len(perms)}")
if len(sys.argv) > 2 and sys.argv[2] == "--permissions":
    for p in perms:
        print(f"    - {p}")
PY

echo
echo "cookie saved to /tmp/threadeye_cookies.txt"
echo "reuse it with:  curl -b /tmp/threadeye_cookies.txt ${API}/<endpoint>"
