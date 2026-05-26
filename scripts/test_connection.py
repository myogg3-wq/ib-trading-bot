"""
Connection Test Script.
Tests all system components individually.

Usage: python scripts/test_connection.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def docker_host_hint(error: Exception, service_name: str) -> str:
    """Provide actionable hint for common local-vs-docker hostname mistakes."""
    text = str(error)
    if "nodename nor servname provided" in text and service_name in ("db", "redis"):
        if service_name == "db":
            return " (docker 외부 실행 중이면 DATABASE_URL host를 localhost로 설정하세요)"
        return " (docker 외부 실행 중이면 REDIS_URL host를 localhost로 설정하세요)"
    return ""


def result(name, success, detail=""):
    global PASS, FAIL
    if success:
        print(f"  ✅ {name}: OK {detail}")
        PASS += 1
    else:
        print(f"  ❌ {name}: FAILED {detail}")
        FAIL += 1


async def test_all():
    global PASS, FAIL

    print("╔══════════════════════════════════════╗")
    print("║   Connection Test Suite               ║")
    print("╚══════════════════════════════════════╝")
    print()

    # --- 1. Config ---
    print("━━━ Configuration ━━━")
    try:
        from app.config import settings
        result("Config loaded", True)
        result("Webhook secret set", settings.webhook_secret != "change_me",
               "(still default!)" if settings.webhook_secret == "change_me" else "")
        result("Telegram token set", bool(settings.telegram_bot_token),
               "(not set!)" if not settings.telegram_bot_token else "")
    except Exception as e:
        result("Config", False, str(e))

    print()

    # --- 2. Database ---
    print("━━━ Database ━━━")
    try:
        from app.database.connection import init_db, get_session, get_bot_settings
        await init_db()
        result("DB connection", True)

        async with get_session() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        result("DB query", True)

        bot_settings = await get_bot_settings()
        result("Bot settings", True, f"(buy=${bot_settings.buy_amount_usd})")
    except Exception as e:
        result("Database", False, str(e) + docker_host_hint(e, "db"))

    print()

    # --- 3. Redis ---
    print("━━━ Redis ━━━")
    try:
        from app.queue.order_queue import get_redis, get_queue_stats
        r = await get_redis()
        await r.ping()
        result("Redis connection", True)

        stats = await get_queue_stats()
        result("Queue stats", True, f"(total: {stats['total']})")
    except Exception as e:
        result("Redis", False, str(e) + docker_host_hint(e, "redis"))

    print()

    # --- 4. IB Gateway ---
    print("━━━ IB Gateway ━━━")
    try:
        from app.broker.ib_client import IBClient
        ib = IBClient()
        connected = await ib.connect()
        result("IB Gateway connection", connected)

        if connected:
            cash = await ib.get_available_cash()
            result("Account data", True, f"(cash=${cash:,.2f})")

            positions = await ib.get_positions()
            result("Positions query", True, f"({len(positions)} positions)")

            await ib.disconnect()
    except Exception as e:
        result("IB Gateway", False, str(e))
        print("    (Is IB Gateway running? Check: sudo systemctl status ib-gateway)")

    print()

    # --- 5. Telegram ---
    print("━━━ Telegram ━━━")
    try:
        from app.notifications.telegram_bot import send_notification
        sent = await send_notification("🧪 Test message from IB Trading Bot")
        result("Telegram notification", sent, "(check your Telegram!)" if sent else "(send failed)")
    except Exception as e:
        result("Telegram", False, str(e))

    print()

    # --- 6. Market Hours ---
    print("━━━ Market Hours ━━━")
    try:
        from app.broker.market_hours import get_market_status
        market = get_market_status()
        result("Market status", True,
               f"({market['emoji']} {market['status']}, {market['current_time_et']})")
    except Exception as e:
        result("Market hours", False, str(e))

    print()

    # --- Summary ---
    print("══════════════════════════════════════")
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("══════════════════════════════════════")

    if FAIL == 0:
        print("🎉 All systems operational!")
    else:
        print("⚠️  Some components need attention.")

    return FAIL


if __name__ == "__main__":
    failures = asyncio.run(test_all())
    sys.exit(1 if failures > 0 else 0)
