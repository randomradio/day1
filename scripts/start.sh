#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-all}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

start_api() {
  echo "[day1] starting api on http://127.0.0.1:8000"
  exec uv run uvicorn day1.api.app:app --host 127.0.0.1 --port 8000 --reload
}

start_dashboard() {
  echo "[day1] starting dashboard on http://127.0.0.1:5173"
  cd "$ROOT/dashboard"
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  exec npm run dev
}

start_all() {
  echo "[day1] checking db"
  uv run "$ROOT/scripts/check_db.py" || true

  (
    cd "$ROOT"
    uv run uvicorn day1.api.app:app --host 127.0.0.1 --port 8000 --reload
  ) &
  api_pid=$!

  (
    cd "$ROOT/dashboard"
    if [[ ! -d node_modules ]]; then
      npm install
    fi
    npm run dev
  ) &
  dashboard_pid=$!

  trap 'kill $api_pid $dashboard_pid 2>/dev/null || true' EXIT INT TERM
  wait -n $api_pid $dashboard_pid
}

case "$MODE" in
  api)
    cd "$ROOT"
    start_api
    ;;
  dashboard)
    start_dashboard
    ;;
  all)
    start_all
    ;;
  *)
    echo "Usage: bash scripts/start.sh [all|api|dashboard]" >&2
    exit 1
    ;;
esac

