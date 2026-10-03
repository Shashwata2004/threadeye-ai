#!/bin/sh
# api:    wait for Postgres → migrate → (optional) seed demo users → serve
# worker: wait for Postgres → run the background worker
set -eu

wait_for_db() {
  python - <<'PY'
import sys, time
from threadeye.db.session import ping
for attempt in range(60):
    try:
        if ping():
            sys.exit(0)
    except Exception:
        pass
    time.sleep(1)
print("database not reachable after 60 s", file=sys.stderr)
sys.exit(1)
PY
}

case "${1:-api}" in
  api)
    wait_for_db
    threadeye migrate
    if [ "${THREADEYE_SEED_DEMO_USERS:-false}" = "true" ]; then
      threadeye seed-demo-users || echo "demo users not seeded"
    fi
    exec uvicorn threadeye.api.app:app --host 0.0.0.0 --port 8000 \
      --proxy-headers --forwarded-allow-ips="*" --no-server-header
    ;;
  worker)
    wait_for_db
    exec python -m threadeye.jobs.worker
    ;;
  *)
    exec "$@"
    ;;
esac
