#!/usr/bin/env bash
# The competition demo on a laptop: the app against the shared Supabase database (like run_cloud.sh),
# with ThreadEye's trained detector (YOLOX, ONNX Runtime on the CPU) instead of the simulated one.
#
#   ./scripts/run_demo.sh   →   http://localhost:3000
#
# The first run installs Python/Node packages. Demo videos and the stable model are bundled in Git;
# Supabase asset fetching is a compatibility fallback for older/incomplete checkouts.
# Needs: .env.cloud (ask Shashwata: it holds the database password), uv, Node.js with pnpm.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="${CLOUD_ENV:-.env.cloud}"
MODEL_DIR="$PWD/data/model"

[ -f "$ENV_FILE" ] || { echo "$ENV_FILE is missing: get it from Shashwata and put it in $PWD" >&2; exit 1; }
# Desktop terminals may not inherit the PATH set by uv's installer.
if ! command -v uv >/dev/null 2>&1; then
  for uv_bin_dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -x "$uv_bin_dir/uv" ]; then
      export PATH="$uv_bin_dir:$PATH"
      break
    fi
  done
fi
command -v uv >/dev/null || { echo "uv is missing: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2; exit 1; }
command -v pnpm >/dev/null || { echo "pnpm is missing: install Node.js 20+, then: npm i -g pnpm" >&2; exit 1; }

echo "checking Python packages"
(cd backend && uv sync --frozen --extra vision --extra onnx --quiet)
if [ ! -d frontend/node_modules ]; then
  echo "installing the web app's packages (first run only)"
  (cd frontend && pnpm install --frozen-lockfile)
fi

if python3 scripts/check_demo_assets.py; then
  echo "using the bundled demo videos and stable trained model"
else
  echo "fetching missing assets from Supabase (older/incomplete checkout)"
  (set -a && . "./$ENV_FILE" && set +a && cd backend && .venv/bin/threadeye fetch-demo-assets --data ../data --model-dir "$MODEL_DIR")
  # The downloader verifies stored hashes and preserves a validated local activation. Such a model
  # can legitimately differ from the bundled baseline; do not overwrite or reject that activation.
fi

DEMO_MODEL_DIR="$MODEL_DIR" exec ./scripts/run_cloud.sh
