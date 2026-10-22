#!/usr/bin/env bash
# Deploy the cloud demo to Vercel (free Hobby plan): two projects, both in Tokyo (hnd1) next to the
# Supabase database (ap-northeast-1).
#
#   threadeye-api  FastAPI (Vercel's FastAPI support, app.py). Built from build/vercel-api/: the backend package,
#                  the simulated rolls' CSV/JSON (no video: that is served from Supabase, see
#                  `make cloud-upload-video`) and pinned requirements.
#   threadeye-web  Next.js. It forwards /api and /health to threadeye-api (API_ORIGIN), so the browser
#                  talks to one origin and the login cookie stays first-party.
#
# Needs: the Vercel CLI logged in (`vercel login`), uv, and a working .env.cloud.
#   ./scripts/deploy_vercel.sh            build + deploy both (sets the env vars on the first run)
#   ./scripts/deploy_vercel.sh api|web    one of them
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
ENV_FILE="${CLOUD_ENV:-.env.cloud}"
API_PROJECT="${API_PROJECT:-threadeye-api}"
WEB_PROJECT="${WEB_PROJECT:-threadeye-web}"
WHAT="${1:-all}"

python3 scripts/check_cloud_env.py "$ENV_FILE"
command -v vercel >/dev/null || { echo "Vercel CLI missing: npm i -g vercel" >&2; exit 1; }

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Set (or replace) a production env var without printing its value.
set_env() {
  local dir="$1" name="$2" value="$3"
  (cd "$dir" && vercel env rm "$name" production --yes >/dev/null 2>&1 || true)
  (cd "$dir" && printf '%s' "$value" | vercel env add "$name" production >/dev/null)
  echo "  env $name set"
}

prod_url() {  # the stable production domain of a linked project
  local dir="$1" name="$2" url
  url="$( (cd "$dir" && vercel project inspect "$name" 2>&1) | grep -oE 'https://[a-z0-9-]+\.vercel\.app' | head -1 || true)"
  # Newer CLIs no longer print the domain; a project's production alias is <name>.vercel.app.
  echo "${url:-https://$name.vercel.app}"
}

build_api() {
  local out="$ROOT/build/vercel-api" UV
  UV="$(command -v uv || true)"
  [ -n "$UV" ] || { echo "uv missing (needed to pin the Python requirements)" >&2; exit 1; }
  rm -rf "$out/api" "$out/app.py" "$out/threadeye" "$out/datasets"
  mkdir -p "$out/datasets"
  rsync -a --exclude '__pycache__' "$ROOT/backend/threadeye" "$out/"
  # Only the rolls that are in git (local test rolls such as data/ci_roll stay out).
  for meta in $(git -C "$ROOT" ls-files 'data/*/roll_meta.json'); do
    d="$ROOT/$(dirname "$meta")"
    [ -f "$d/frames.csv" ] || continue
    name="$(basename "$d")"
    mkdir -p "$out/datasets/$name"
    cp "$d"/*.csv "$d"/roll_meta.json "$out/datasets/$name/"
    [ -f "$d/HIDDEN" ] && cp "$d/HIDDEN" "$out/datasets/$name/"
  done
  (cd "$ROOT/backend" && "$UV" export --frozen --no-dev --no-hashes --no-emit-project --no-header \
    | grep -v '^ *#' > "$out/requirements.txt")
  echo "tzdata" >> "$out/requirements.txt"  # Asia/Dhaka for report times; the function image may lack it
  # Vercel's FastAPI support finds `app` in app.py and routes every path to it, unchanged.
  cat > "$out/app.py" <<'PY'
"""Vercel entry point: the whole FastAPI app as one Python function (cloud_demo profile)."""

from threadeye.api.app import app

__all__ = ["app"]
PY
  cat > "$out/vercel.json" <<'JSON'
{
  "regions": ["hnd1"],
  "framework": "fastapi"
}
JSON
  printf '.vercel\n' > "$out/.vercelignore"
  echo "built $out ($(du -sh "$out" | cut -f1))"
}

deploy_api() {
  build_api
  local dir="$ROOT/build/vercel-api" web_url
  (cd "$dir" && vercel link --yes --project "$API_PROJECT" >/dev/null)
  web_url="${WEB_URL:-$(prod_url "$ROOT/frontend" "$WEB_PROJECT" || true)}"
  if [ -n "${SET_ENV:-}" ] || [ ! -f "$dir/.env-set" ]; then
    set_env "$dir" THREADEYE_DEPLOY_PROFILE cloud_demo
    set_env "$dir" THREADEYE_DATABASE_URL "$THREADEYE_DATABASE_URL"
    set_env "$dir" THREADEYE_COOKIE_SECURE true
    set_env "$dir" THREADEYE_DATASETS_DIR /var/task/datasets
    [ -n "$web_url" ] && set_env "$dir" THREADEYE_ALLOWED_ORIGINS "$web_url"
    touch "$dir/.env-set"
  fi
  (cd "$dir" && vercel deploy --prod --yes)
}

deploy_web() {
  (cd "$ROOT/frontend" && vercel link --yes --project "$WEB_PROJECT" >/dev/null)
  local api_url
  api_url="${API_URL:-$(prod_url "$ROOT/build/vercel-api" "$API_PROJECT")}"
  [ -n "$api_url" ] || { echo "deploy the API first (./scripts/deploy_vercel.sh api)" >&2; exit 1; }
  set_env "$ROOT/frontend" API_ORIGIN "$api_url"
  set_env "$ROOT/frontend" NEXT_TELEMETRY_DISABLED 1
  (cd "$ROOT/frontend" && vercel deploy --prod --yes)
}

case "$WHAT" in
  api) deploy_api ;;
  web) deploy_web ;;
  all) deploy_api && deploy_web ;;
  *) echo "usage: $0 [api|web|all]" >&2; exit 2 ;;
esac
