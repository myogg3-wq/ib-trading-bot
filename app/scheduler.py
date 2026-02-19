"""
APScheduler jobs for automated tasks:
- Market open: flush pending queue
- Daily report
- Periodic position sync
- Sunday login reminder
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()


async def job_market_open():
    """
    Runs at 09:30 ET every weekday.
    Moves pending orders to active queues.
    """
    from app.queue.order_queue import flush_pending_to_active
    from app.notifications.telegram_bot import send_notification

    count = await flush_pending_to_active()
    if count > 0:
        await send_notification(
            f"🔔 Market Open!\n"
            f"📤 {count} pending orders moved to active queue."
        )
    else:
        logger.info("Market open — no pending orders")


async def job_daily_report():
    """
    Runs at 16:05 ET every weekday (5 min after market close).
    Sends daily performance report.
    """
    from app.notifications.telegram_bot import send_daily_report
    await send_daily_report()


async def job_position_sync():
    """
    Runs every 4 hours during market hours.
    Checks for position mismatches.
    """
    from app.broker.position_sync import sync_positions, format_sync_report
    from app.notifications.telegram_bot import send_notification
    from app.broker.market_hours import is_market_open

    if not is_market_open():
        return

    result = await sync_positions()
    if result["status"] == "mismatch":
        report = format_sync_report(result)
        await send_notification(report)


async def job_sunday_reminder():
    """
    Runs every Sunday at 10:00 ET.
    Reminds to log in to IB Gateway.
    """
    from app.notifications.telegram_bot import send_notification
    await send_notification(
        "⚠️ Sunday IB Re-authentication Required!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Please log in to IB Gateway before Monday market open.\n"
        "Connect to VPS and authenticate.\n"
        "\n"
        "⏰ Market opens Monday 9:30 AM ET"
    )


async def job_health_check():
    """
    Runs every 5 minutes.
    Checks IB connection and sends alert if disconnected.
    """
    from app.broker.ib_client import get_ib_client
    from app.notifications.telegram_bot import send_notification

    try:
        ib = await get_ib_client()
        if not ib.is_connected:
            await send_notification(
                "🔴 IB Gateway DISCONNECTED!\n"
                "Auto-reconnect is attempting..."
            )
    except Exception as e:
        logger.error("Health check failed", error=str(e))


def setup_scheduler():
    """Configure and start the scheduler."""
    # Market open — flush pending queue (9:30 ET, Mon-Fri)
    scheduler.add_job(
        job_market_open,
        CronTrigger(hour=9, minute=30, day_of_week="mon-fri", timezone="US/Eastern"),
        id="market_open",
        name="Market Open — Flush Pending Queue",
        replace_existing=True,
    )

    # Daily report (16:05 ET, Mon-Fri)
    scheduler.add_job(
        job_daily_report,
        CronTrigger(hour=16, minute=5, day_of_week="mon-fri", timezone="US/Eastern"),
        id="daily_report",
        name="Daily Performance Report",
        replace_existing=True,
    )

    # Position sync (every 4 hours, Mon-Fri)
    scheduler.add_job(
        job_position_sync,
        CronTrigger(hour="10,14,18", day_of_week="mon-fri", timezone="US/Eastern"),
        id="position_sync",
        name="Position Sync Check",
        replace_existing=True,
    )

    # Sunday IB login reminder (Sunday 10:00 ET)
    scheduler.add_job(
        job_sunday_reminder,
        CronTrigger(hour=10, day_of_week="sun", timezone="US/Eastern"),
        id="sunday_reminder",
        name="Sunday IB Login Reminder",
        replace_existing=True,
    )

    # Health check (every 5 minutes)
    scheduler.add_job(
        job_health_check,
        "interval",
        minutes=5,
        id="health_check",
        name="IB Health Check",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with all jobs")

    return scheduler
