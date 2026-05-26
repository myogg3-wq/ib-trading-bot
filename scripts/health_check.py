"""Manual website and infrastructure health check script."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import httpx
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.web.site_monitor import collect_site_report, summarize_report


async def check_health(*, notify: bool = False) -> int:
    """Check core system components and the public site."""
    results = {}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.site_monitor_base_url.rstrip('/')}/health", timeout=5)
            results["api"] = "OK" if resp.status_code == 200 else f"FAIL ({resp.status_code})"
    except Exception as e:
        results["api"] = f"FAIL ({str(e)})"

    try:
        import redis.asyncio as redis

        redis_client = redis.from_url(settings.redis_url)
        await redis_client.ping()
        results["redis"] = "OK"
        await redis_client.aclose()
    except Exception as e:
        results["redis"] = f"FAIL ({str(e)})"

    try:
        from app.database.connection import get_session

        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        results["postgres"] = "OK"
    except Exception as e:
        results["postgres"] = f"FAIL ({str(e)})"

    try:
        from app.broker.ib_client import get_ib_client

        ib = await get_ib_client()
        results["ib_gateway"] = "OK" if ib.is_connected else "DISCONNECTED"
    except Exception as e:
        results["ib_gateway"] = f"FAIL ({str(e)})"

    site_report = await collect_site_report()

    print("=" * 48)
    print("Infrastructure Health")
    print("=" * 48)

    all_ok = True
    for component, status in results.items():
        icon = "✓" if status == "OK" else "✗"
        print(f"  {icon} {component}: {status}")
        if status != "OK":
            all_ok = False

    print()
    print("=" * 48)
    print("Website Health")
    print("=" * 48)
    print(summarize_report(site_report))

    if notify:
        from app.notifications.telegram_bot import send_notification

        await send_notification(summarize_report(site_report))

    overall_ok = all_ok and site_report["overall_status"] == "healthy"
    print("=" * 48)
    print(f"Overall: {'ALL OK' if overall_ok else 'ISSUES FOUND'}")
    return 0 if overall_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run infrastructure and website health checks.")
    parser.add_argument("--notify", action="store_true", help="Send the site report to Telegram.")
    args = parser.parse_args()
    return asyncio.run(check_health(notify=args.notify))


if __name__ == "__main__":
    sys.exit(main())
