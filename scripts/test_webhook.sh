#!/bin/bash
# ============================================
# Webhook Test Script
# Tests all scenarios against your running server
#
# Usage: bash scripts/test_webhook.sh [URL] [SECRET]
# Default: http://localhost:8000 (local testing)
# ============================================

URL=${1:-"http://localhost:8000"}
SECRET=${2:-"your_strong_secret_key_here"}

echo "╔══════════════════════════════════════╗"
echo "║   Webhook Test Suite                  ║"
echo "╚══════════════════════════════════════╝"
echo "URL: $URL"
echo ""

PASS=0
FAIL=0

run_test() {
    local name=$1
    local expected_status=$2
    local data=$3
    local extra_args=$4

    response=$(curl -s -o /tmp/test_response.json -w "%{http_code}" \
        -X POST "$URL/webhook" \
        -H "Content-Type: application/json" \
        $extra_args \
        -d "$data" 2>&1)

    body=$(cat /tmp/test_response.json 2>/dev/null)

    if [ "$response" = "$expected_status" ]; then
        echo "✅ PASS: $name (HTTP $response)"
        PASS=$((PASS + 1))
    else
        echo "❌ FAIL: $name (Expected $expected_status, got $response)"
        echo "   Response: $body"
        FAIL=$((FAIL + 1))
    fi
}

# --- Test 1: Valid BUY ---
echo "━━━ Basic Tests ━━━"
run_test "Valid BUY" "200" \
    "{\"secret\":\"$SECRET\",\"action\":\"BUY\",\"ticker\":\"AAPL\",\"price\":\"150.00\",\"alert_id\":\"test_buy_1\"}"

sleep 1

# --- Test 2: Valid SELL ---
run_test "Valid SELL" "200" \
    "{\"secret\":\"$SECRET\",\"action\":\"SELL\",\"ticker\":\"AAPL\",\"price\":\"155.00\",\"alert_id\":\"test_sell_1\"}"

sleep 1

# --- Test 3: BUY with exchange prefix ---
run_test "BUY with NASDAQ prefix" "200" \
    "{\"secret\":\"$SECRET\",\"action\":\"BUY\",\"ticker\":\"NASDAQ:TSLA\",\"price\":\"250.00\",\"alert_id\":\"test_buy_2\"}"

echo ""
echo "━━━ Security Tests ━━━"

# --- Test 4: Wrong secret ---
run_test "Wrong secret → Rejected" "401" \
    "{\"secret\":\"wrong_secret\",\"action\":\"BUY\",\"ticker\":\"AAPL\"}"

# --- Test 5: No secret ---
run_test "No secret → Rejected" "401" \
    "{\"action\":\"BUY\",\"ticker\":\"AAPL\"}"

# --- Test 6: Empty body ---
run_test "Empty body → Rejected" "400" ""

echo ""
echo "━━━ Validation Tests ━━━"

# --- Test 7: Invalid action ---
run_test "Invalid action → Rejected" "400" \
    "{\"secret\":\"$SECRET\",\"action\":\"HOLD\",\"ticker\":\"AAPL\"}"

# --- Test 8: Missing ticker ---
run_test "Missing ticker → Rejected" "400" \
    "{\"secret\":\"$SECRET\",\"action\":\"BUY\",\"ticker\":\"\"}"

# --- Test 9: Duplicate alert_id ---
run_test "Duplicate alert → Skipped" "200" \
    "{\"secret\":\"$SECRET\",\"action\":\"BUY\",\"ticker\":\"AAPL\",\"price\":\"150.00\",\"alert_id\":\"test_buy_1\"}"

echo ""
echo "━━━ Health Check ━━━"

health_response=$(curl -s -o /dev/null -w "%{http_code}" "$URL/health")
if [ "$health_response" = "200" ]; then
    echo "✅ PASS: Health check (HTTP $health_response)"
    PASS=$((PASS + 1))
else
    echo "❌ FAIL: Health check (HTTP $health_response)"
    FAIL=$((FAIL + 1))
fi

# --- Summary ---
echo ""
echo "══════════════════════════════════════"
echo "Results: $PASS passed, $FAIL failed"
echo "══════════════════════════════════════"

if [ $FAIL -eq 0 ]; then
    echo "🎉 All tests passed!"
    exit 0
else
    echo "⚠️  Some tests failed. Check your server."
    exit 1
fi
