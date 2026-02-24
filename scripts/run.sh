#!/usr/bin/env bash
# Quick start script for BranchedMind
# Usage: bash scripts/run.sh [test|api|dashboard|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# ─── helpers ────────────────────────────────────────────
info()  { echo "==> $*"; }
error() { echo "ERROR: $*" >&2; exit 1; }

check_uv() {
    if ! command -v uv &>/dev/null; then
        error "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
}

install_deps() {
    check_uv
    info "Syncing Python dependencies via uv..."
    uv sync --all-extras
}

# ─── commands ───────────────────────────────────────────
cmd_test() {
    check_uv
    info "Running MO feature tests..."
    uv run python scripts/test_mo_features.py
}

cmd_api() {
    check_uv
    info "Starting FastAPI server on http://127.0.0.1:8000 ..."
    info "  Docs: http://127.0.0.1:8000/docs"
    info "  Health: http://127.0.0.1:8000/health"
    uv run uvicorn branchedmind.api.app:app --reload --host 127.0.0.1 --port 8000
}

cmd_dashboard() {
    if [ ! -d "dashboard/node_modules" ]; then
        info "Installing dashboard dependencies..."
        (cd dashboard && npm install)
    fi
    info "Starting dashboard on http://localhost:5173 ..."
    (cd dashboard && npm run dev)
}

cmd_all() {
    install_deps
    info ""
    info "Step 1: Verify MO connection"
    cmd_test
    info ""
    info "Step 2: Starting API server (background)..."
    uv run uvicorn branchedmind.api.app:app --reload --host 127.0.0.1 --port 8000 &
    API_PID=$!
    sleep 2
    info "  API PID: $API_PID"
    info ""
    info "Step 3: Starting dashboard..."
    cmd_dashboard
    # Cleanup on exit
    kill "$API_PID" 2>/dev/null || true
}

# ─── main ───────────────────────────────────────────────
case "${1:-help}" in
    test)       cmd_test ;;
    api)        cmd_api ;;
    dashboard)  cmd_dashboard ;;
    all)        cmd_all ;;
    install)    install_deps ;;
    *)
        echo "BranchedMind - Quick Start"
        echo ""
        echo "Usage: bash scripts/run.sh <command>"
        echo ""
        echo "Commands:"
        echo "  install     Sync Python dependencies (uv sync)"
        echo "  test        Verify MO connection & features"
        echo "  api         Start FastAPI server (:8000)"
        echo "  dashboard   Start React dashboard (:5173)"
        echo "  all         Test + API + Dashboard"
        echo ""
        echo "Requires: uv (https://docs.astral.sh/uv/)"
        echo "Set BM_DATABASE_URL in .env (see .env.example)."
        ;;
esac
