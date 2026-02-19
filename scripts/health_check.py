"""
Health check script.
Can be called by UptimeRobot or cron to verify system is running.

Usage:
    python -m scripts.health_check
"""

import asyncio
import sys
import os
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def check_health():
    """Check all system components."""
    results = {}

    # 1. Check FastAPI
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/health", timeout=5)
            results["api"] = "OK" if resp.status_code == 200 else f"FAIL ({resp.status_code})"
    except Exception as e:
        results["api"] = f"FAIL ({str(e)})"

    # 2. Check Redis
    try:
        import redis.asyncio as redis
        r = redis.from_url("redis://localhost:6379/0")
        await r.ping()
        results["redis"] = "OK"
        await r.close()
    except Exception as e:
        results["redis"] = f"FAIL ({str(e)})"

    # 3. Check PostgreSQL
    try:
        from app.database.connection import get_session
        async with get_session() as session:
            await session.execute("SELECT 1")
        results["postgres"] = "OK"
    except Exception as e:
        results["postgres"] = f"FAIL ({str(e)})"

    # 4. Check IB Gateway
    try:
        from app.broker.ib_client import get_ib_client
        ib = await get_ib_client()
        results["ib_gateway"] = "OK" if ib.is_connected else "DISCONNECTED"
    except Exception as e:
        results["ib_gateway"] = f"FAIL ({str(e)})"

    # Print results
    print("=" * 40)
    print("Health Check Results")
    print("=" * 40)

    all_ok = True
    for component, status in results.items():
        icon = "✓" if status == "OK" else "✗"
        print(f"  {icon} {component}: {status}")
        if status != "OK":
            all_ok = False

    print("=" * 40)
    print(f"Overall: {'ALL OK' if all_ok else 'ISSUES FOUND'}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    exit_code = asyncio.run(check_health())
    sys.exit(exit_code)
