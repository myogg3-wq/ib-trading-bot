#!/usr/bin/env python3
"""
Test webhook integration with sample BUY/SELL signals.
Simulates TradingView alerts.
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

# Configuration
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_me")
LIVE_WEBHOOK_TEST_CONFIRMATION = "YES_I_UNDERSTAND_THIS_CAN_QUEUE_REAL_ORDERS"


def _is_local_webhook_url(url: str) -> bool:
    """Return True only for local webhook targets that cannot hit live queues."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _should_block_non_local_target() -> bool:
    """Protect live queues from accidental sample BUY/SELL alerts."""
    if _is_local_webhook_url(WEBHOOK_URL):
        return False
    return os.getenv("ALLOW_LIVE_WEBHOOK_TEST") != LIVE_WEBHOOK_TEST_CONFIRMATION


def send_alert(action: str, ticker: str, price: Optional[float] = None) -> bool:
    """Send a test alert to the webhook."""
    import requests

    payload = {
        "secret": WEBHOOK_SECRET,
        "action": action.upper(),
        "ticker": ticker.upper(),
        "price": price,
        "time": datetime.now().isoformat(),
        "alert_id": f"test_{action.lower()}_{ticker.lower()}_{datetime.now().timestamp()}",
    }

    print(f"\n📤 Sending {action.upper()} alert for {ticker.upper()}...")
    print(f"   Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=5,
        )

        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")

        if response.status_code in (200, 202):
            print(f"✅ Alert received and queued")
            return True
        else:
            print(f"❌ Alert rejected: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"❌ Connection error. Is the API server running?")
        print(f"   Try: uvicorn app.main:app --host 0.0.0.0 --port 8000")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_health() -> bool:
    """Test if API is healthy."""
    import requests

    print("🔍 Testing API health...")
    try:
        response = requests.get(f"{WEBHOOK_URL.rsplit('/', 1)[0]}/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ API is healthy")
            return True
        else:
            print(f"❌ API returned {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to API at {WEBHOOK_URL}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def run_scenarios():
    """Run a series of test scenarios."""
    print("\n" + "=" * 50)
    print("🧪 Webhook Integration Test Suite")
    print("=" * 50)

    # Test health
    if not test_health():
        print("\n❌ API is not accessible!")
        print("\nTo run the API server:")
        print("  uvicorn app.main:app --host 0.0.0.0 --port 8000")
        return False

    print("\n" + "-" * 50)
    print("🎯 Running test scenarios...")
    print("-" * 50)

    scenarios = [
        ("BUY", "AAPL", 150.25),
        ("BUY", "MSFT", 380.50),
        ("BUY", "TSLA", 250.00),
        ("SELL", "AAPL", 152.00),
        ("SELL", "MSFT", 385.00),
        ("BUY", "GOOGL", 140.00),
        ("SELL", "TSLA", 255.00),
        ("BUY", "NVDA", 500.00),
    ]

    results = {}
    for action, ticker, price in scenarios:
        results[f"{action}_{ticker}"] = send_alert(action, ticker, price)

    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {test_name}")

    print(f"\n{passed}/{total} alerts processed successfully")

    if passed == total:
        print("\n✅ All tests passed!")
        print("\n📝 Next steps:")
        print("1. Check Telegram /status to see bot status")
        print("2. Check Telegram /positions to see open positions")
        print("3. Check Telegram /pnl to see today's P&L")
        return True
    else:
        print("\n⚠️ Some tests failed")
        print("Check logs: docker-compose logs api")
        return False


def test_invalid_secret():
    """Test that invalid secret is rejected."""
    import requests

    print("\n" + "-" * 50)
    print("🔒 Testing security...")
    print("-" * 50)

    print("\n📤 Sending alert with WRONG secret...")

    payload = {
        "secret": "wrong_secret_1234567890",
        "action": "BUY",
        "ticker": "AAPL",
        "price": 150.00,
    }

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)

        if response.status_code == 401:
            print(f"✅ Correctly rejected invalid secret")
            return True
        else:
            print(f"❌ Should reject invalid secret (got {response.status_code})")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_invalid_action():
    """Test that invalid action is rejected."""
    import requests

    print("\n📤 Sending alert with INVALID action...")

    payload = {
        "secret": WEBHOOK_SECRET,
        "action": "HOLD",  # Invalid
        "ticker": "AAPL",
        "price": 150.00,
    }

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)

        if response.status_code == 400:
            print(f"✅ Correctly rejected invalid action")
            return True
        else:
            print(f"❌ Should reject invalid action (got {response.status_code})")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Main entry point."""
    print("\n" + "=" * 50)
    print("IB Trading Bot - Webhook Test Suite")
    print("=" * 50)

    if _should_block_non_local_target():
        print("\n❌ Refusing to send sample alerts to a non-local webhook target.")
        print(f"   WEBHOOK_URL={WEBHOOK_URL}")
        print("   This script can enqueue real BUY/SELL orders when pointed at production.")
        print("\n   For local testing, use:")
        print("   WEBHOOK_URL=http://localhost:8000/webhook")
        print("\n   If you intentionally want a live queue test, set:")
        print(f"   ALLOW_LIVE_WEBHOOK_TEST={LIVE_WEBHOOK_TEST_CONFIRMATION}")
        return 2

    # Check configuration
    if WEBHOOK_SECRET == "change_me":
        print("\n⚠️ Warning: Using default webhook secret!")
        print("   Update WEBHOOK_SECRET in this script to match your .env")
        print("\n📝 Your secret from .env:")
        print("   .env: WEBHOOK_SECRET=<your_secret>")

    # Run main test suite
    if not run_scenarios():
        return 1

    # Run security tests
    if not test_invalid_secret():
        print("\n⚠️ Security issue: Invalid secret not rejected!")

    if not test_invalid_action():
        print("\n⚠️ Validation issue: Invalid action not rejected!")

    # Final summary
    print("\n" + "=" * 50)
    print("✅ Webhook Test Complete!")
    print("=" * 50)

    print("\n📚 Next Steps:")
    print("1. Monitor bot via Telegram:")
    print("   /status   - Check bot status")
    print("   /queue    - Check pending orders")
    print("   /positions - See open positions")
    print("\n2. Check worker processing:")
    print("   docker-compose logs worker -f")
    print("\n3. Configure TradingView alerts:")
    print("   See: tradingview/HOW_TO_SETUP_ALERTS.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
