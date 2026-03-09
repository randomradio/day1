#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-all}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${BM_PORT:-9821}"

start_api() {
  echo "[day1] starting go api on http://0.0.0.0:${API_PORT}"
  cd "$ROOT"
  exec env BM_PORT="${API_PORT}" go run ./cmd/day1-api
}

start_all() {
  echo "[day1] checking db connectivity"
  bash "$ROOT/scripts/check_db.sh" || true
  start_api
}

case "$MODE" in
  api)
    start_api
    ;;
  all)
    start_all
    ;;
  *)
    echo "Usage: bash scripts/start.sh [all|api]" >&2
    exit 1
    ;;
esac
