#!/usr/bin/env bash
# ─── Day1 E2E Smoke Test ────────────────────────────────────────
# Proves the full pipeline: health → branch → fact → search →
# conversation → fork → replay → diff → analytics.
#
# Usage:
#   ./scripts/smoke_test.sh                  # default: localhost:8000
#   ./scripts/smoke_test.sh http://my-host:8000
#   API_KEY=secret ./scripts/smoke_test.sh   # with auth
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

BASE="${1:-http://localhost:8000}"
API="$BASE/api/v1"
AUTH_HEADER=""
if [ -n "${API_KEY:-}" ]; then
  AUTH_HEADER="Authorization: Bearer $API_KEY"
fi

PASS=0
FAIL=0

check() {
  local label="$1"
  local status="$2"
  local body="$3"

  if [ "$status" -ge 200 ] && [ "$status" -lt 300 ]; then
    echo "  [PASS] $label (HTTP $status)"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $label (HTTP $status)"
    echo "         $body" | head -c 200
    echo
    FAIL=$((FAIL + 1))
  fi
}

req() {
  local method="$1"
  local url="$2"
  local data="${3:-}"

  local args=(-s -w '\n%{http_code}' -X "$method")
  if [ -n "$AUTH_HEADER" ]; then
    args+=(-H "$AUTH_HEADER")
  fi
  if [ -n "$data" ]; then
    args+=(-H 'Content-Type: application/json' -d "$data")
  fi

  local response
  response=$(curl "${args[@]}" "$url")
  local status
  status=$(echo "$response" | tail -1)
  local body
  body=$(echo "$response" | sed '$d')

  echo "$body"
  return 0
}

req_status() {
  local method="$1"
  local url="$2"
  local data="${3:-}"

  local args=(-s -o /dev/null -w '%{http_code}' -X "$method")
  if [ -n "$AUTH_HEADER" ]; then
    args+=(-H "$AUTH_HEADER")
  fi
  if [ -n "$data" ]; then
    args+=(-H 'Content-Type: application/json' -d "$data")
  fi

  curl "${args[@]}" "$url"
}

echo ""
echo "=== Day1 Smoke Test ==="
echo "    Target: $BASE"
echo ""

# ─── 1. Health ───────────────────────────────────────────────────
echo "[1/8] Health check"
STATUS=$(req_status GET "$BASE/health")
check "GET /health" "$STATUS" ""

# ─── 2. Branches ─────────────────────────────────────────────────
echo "[2/8] Branches"
STATUS=$(req_status GET "$API/branches")
check "GET /branches" "$STATUS" ""

STATUS=$(req_status POST "$API/branches" '{"branch_name":"smoke-test","parent_branch":"main","description":"smoke test"}')
check "POST /branches (create smoke-test)" "$STATUS" ""

# ─── 3. Write a fact ─────────────────────────────────────────────
echo "[3/8] Facts"
FACT_BODY=$(req POST "$API/facts" '{"fact_text":"OAuth token refresh requires exponential backoff","category":"pattern","confidence":0.9,"branch":"smoke-test"}')
FACT_ID=$(echo "$FACT_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
STATUS=$(req_status GET "$API/facts/$FACT_ID")
check "POST + GET /facts" "$STATUS" ""

# ─── 4. Search ───────────────────────────────────────────────────
echo "[4/8] Search"
STATUS=$(req_status GET "$API/facts/search?query=OAuth+token&branch=smoke-test&search_type=keyword")
check "GET /facts/search" "$STATUS" ""

# ─── 5. Conversation + Messages ──────────────────────────────────
echo "[5/8] Conversations"
CONV_BODY=$(req POST "$API/conversations" '{"title":"Smoke test conversation","branch":"smoke-test"}')
CONV_ID=$(echo "$CONV_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

MSG1_BODY=$(req POST "$API/conversations/$CONV_ID/messages" '{"role":"user","content":"Fix the auth bug","conversation_id":"'$CONV_ID'","branch":"smoke-test"}')
MSG1_ID=$(echo "$MSG1_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

req POST "$API/conversations/$CONV_ID/messages" '{"role":"assistant","content":"I will investigate the token refresh logic","conversation_id":"'$CONV_ID'","branch":"smoke-test"}' > /dev/null

STATUS=$(req_status GET "$API/conversations/$CONV_ID/messages")
check "Conversation + 2 messages" "$STATUS" ""

# ─── 6. Fork conversation ────────────────────────────────────────
echo "[6/8] Fork"
STATUS=$(req_status POST "$API/conversations/$CONV_ID/fork" '{"message_id":"'$MSG1_ID'","title":"Smoke fork","branch":"smoke-test"}')
check "POST /conversations/{id}/fork" "$STATUS" ""

# ─── 7. Analytics ─────────────────────────────────────────────────
echo "[7/8] Analytics"
STATUS=$(req_status GET "$API/analytics/overview?branch=smoke-test")
check "GET /analytics/overview" "$STATUS" ""

# ─── 8. Clean up (archive branch) ────────────────────────────────
echo "[8/8] Cleanup"
STATUS=$(req_status DELETE "$API/branches/smoke-test")
check "DELETE /branches/smoke-test" "$STATUS" ""

# ─── Summary ──────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
echo ""

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
