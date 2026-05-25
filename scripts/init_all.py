#!/usr/bin/env python3
"""
Complete initialization script for IB Trading Bot.

This script:
1. Creates database and tables
2. Seeds default bot settings
3. Sets up Redis connections
4. Tests IB Gateway connection
5. Validates Telegram bot configuration
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.database.connection import init_db, get_bot_settings
from app.broker.ib_client import get_ib_client
from app.queue.order_queue import get_redis
import structlog

logger = structlog.get_logger()


def docker_host_hint(error: Exception, service_name: str) -> str:
    """Provide actionable hint for common local-vs-docker hostname mistakes."""
    text = str(error)
    if "nodename nor servname provided" in text and service_name in ("db", "redis"):
        if service_name == "db":
            return " (docker 외부 실행 중이면 DATABASE_URL host를 localhost로 설정하세요)"
        return " (docker 외부 실행 중이면 REDIS_URL host를 localhost로 설정하세요)"
    return ""


async def test_postgres() -> bool:
    """Test PostgreSQL connection."""
    print("🔹 Testing PostgreSQL...")
    try:
        await init_db()
        settings_obj = await get_bot_settings()
        print(f"✅ PostgreSQL OK")
        print(f"   Default settings: {settings_obj}")
        return True
    except Exception as e:
        print(f"❌ PostgreSQL failed: {e}{docker_host_hint(e, 'db')}")
        return False


async def test_redis() -> bool:
    """Test Redis connection."""
    print("🔹 Testing Redis...")
    try:
        r = await get_redis()
        await r.ping()
        print(f"✅ Redis OK")
        return True
    except Exception as e:
        print(f"❌ Redis failed: {e}{docker_host_hint(e, 'redis')}")
        return False


async def test_ib_gateway() -> bool:
    """Test IB Gateway connection."""
    print("🔹 Testing IB Gateway...")
    try:
        ib = await get_ib_client()
        if ib.is_connected:
            status = ib.get_status()
            print(f"✅ IB Gateway OK")
            print(f"   Connected at: {status['last_connected_at']}")
            return True
        else:
            print(f"⚠️ IB Gateway connection pending (will auto-retry)")
            return True  # Not a hard failure
    except Exception as e:
        print(f"❌ IB Gateway failed: {e}")
        return False


def test_telegram() -> bool:
    """Test Telegram configuration."""
    print("🔹 Testing Telegram...")
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(f"⚠️ Telegram not configured (optional)")
        return True

    token_preview = settings.telegram_bot_token[:10] + "..." if settings.telegram_bot_token else "EMPTY"
    print(f"✅ Telegram configured (token: {token_preview})")
    return True


def test_trading_defaults() -> bool:
    """Test trading defaults."""
    print("🔹 Checking trading defaults...")
    print(f"   Buy Amount: ${settings.default_buy_amount_usd}")
    print(f"   Max Positions: {settings.default_max_open_positions}")
    print(f"   Max Daily Buys: {settings.default_max_daily_buys}")
    print(f"   Max Investment: ${settings.default_max_total_investment}")
    print(f"   Max Per Ticker: {settings.default_max_per_ticker}")
    print(f"   Max Daily Loss: ${settings.default_max_daily_loss}")
    print(f"   Min Cash Reserve: ${settings.default_min_cash_reserve}")
    print(f"✅ Defaults OK")
    return True


def print_next_steps():
    """Print next steps after initialization."""
    print("\n" + "=" * 50)
    print("✅ Initialization Complete!")
    print("=" * 50)
    print("\n📝 Next Steps:")
    print("1. Start the API server:")
    print("   uvicorn app.main:app --host 0.0.0.0 --port 8000")
    print("\n2. Start the order worker (in another terminal):")
    print("   python app/queue/order_worker.py")
    print("\n3. Start the Telegram bot (in another terminal):")
    print("   python app/notifications/telegram_bot.py")
    print("\n4. Access Telegram bot:")
    print("   /start - Show all commands")
    print("   /status - Current bot status")
    print("   /settings - View current settings")
    print("\n📚 Documentation:")
    print("   SETUP_GUIDE.md - Full setup instructions")
    print("   tradingview/HOW_TO_SETUP_ALERTS.md - TradingView integration")
    print("\n⚠️ Important:")
    print("   - Make sure IB Gateway is running on configured host:port")
    print("   - Ensure PostgreSQL and Redis are accessible")
    print("   - Verify webhook secret in .env matches TradingView alert template")
    print("=" * 50 + "\n")


async def main():
    """Run all initialization checks."""
    print("\n" + "=" * 50)
    print("🤖 IB Trading Bot - Initialization")
    print("=" * 50 + "\n")

    # Configuration summary
    print("📋 Configuration Summary:")
    print(f"   IB Host: {settings.ib_host}:{settings.ib_port}")
    print(f"   Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'localhost'}")
    print(f"   Redis: {settings.redis_url}")
    print(f"   Webhook Port: {settings.webhook_port}")
    print()

    # Run all tests
    tests = [
        ("PostgreSQL", test_postgres),
        ("Redis", test_redis),
        ("IB Gateway", test_ib_gateway),
        ("Telegram", test_telegram),
        ("Trading Defaults", test_trading_defaults),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                results[test_name] = await test_func()
            else:
                results[test_name] = test_func()
        except Exception as e:
            logger.error(f"Test error: {test_name}", error=str(e))
            results[test_name] = False

    # Summary
    print("\n" + "=" * 50)
    print("📊 Initialization Summary:")
    print("=" * 50)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {test_name}")

    print(f"\n{passed}/{total} checks passed")

    if passed == total:
        print_next_steps()
        return 0
    else:
        print("\n❌ Some initialization checks failed!")
        print("Please review the errors above and fix configuration.\n")
        return 1


if __name__ == "__main__":
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
