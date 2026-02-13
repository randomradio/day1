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

ensure_venv() {
    if [ ! -d ".venv" ]; then
        info "Creating virtual environment..."
        python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    info "Using Python: $(python --version) at $(which python)"
}

install_deps() {
    ensure_venv
    info "Installing Python dependencies..."
    pip install -e ".[dev]" -q
}

# ─── commands ───────────────────────────────────────────
cmd_test() {
    ensure_venv
    info "Running MO feature tests..."
    python scripts/test_mo_features.py
}

cmd_api() {
    ensure_venv
    info "Starting FastAPI server on http://127.0.0.1:8000 ..."
    info "  Docs: http://127.0.0.1:8000/docs"
    info "  Health: http://127.0.0.1:8000/health"
    uvicorn branchedmind.api.app:app --reload --host 127.0.0.1 --port 8000
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
    ensure_venv
    uvicorn branchedmind.api.app:app --reload --host 127.0.0.1 --port 8000 &
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
        echo "  install     Install Python dependencies"
        echo "  test        Verify MO connection & features"
        echo "  api         Start FastAPI server (:8000)"
        echo "  dashboard   Start React dashboard (:5173)"
        echo "  all         Test + API + Dashboard"
        echo ""
        echo "MO Cloud connection is pre-configured in config.py."
        echo "Override with: export BM_DATABASE_URL=\"mysql+aiomysql://...\""
        ;;
esac
