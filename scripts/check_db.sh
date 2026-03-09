#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${DAY1_DATABASE_URL:-}" ]]; then
  echo "[day1] DAY1_DATABASE_URL is not set; skipping SQL connectivity check"
  exit 0
fi

cd "$ROOT"
go run ./cmd/day1 migrate >/dev/null
echo "[day1] database schema check ok"
