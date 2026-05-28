"""
APScheduler jobs for automated tasks:
- Market open: flush pending queue
- Daily report
- Periodic position sync
- Sunday login reminder
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import importlib.util
import structlog

from app.config import settings

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()
_last_ib_connected = None

ASIA_MARKET_LABELS = {
    "HKEX": "홍콩장",
    "SSE": "중국 상해장",
    "SZSE": "중국 심천장",
    "TSE": "일본장",
}

ASIA_MARKET_OPEN_SCHEDULES = {
    "HKEX": {
        "timezone": "Asia/Hong_Kong",
        "sessions": ((9, 30, "morning"), (13, 0, "afternoon")),
    },
    "SSE": {
        "timezone": "Asia/Shanghai",
        "sessions": ((9, 30, "morning"), (13, 0, "afternoon")),
    },
    "SZSE": {
        "timezone": "Asia/Shanghai",
        "sessions": ((9, 30, "morning"), (13, 0, "afternoon")),
    },
    "TSE": {
        "timezone": "Asia/Tokyo",
        "sessions": ((9, 0, "morning"), (12, 30, "afternoon")),
    },
}


async def job_market_open():
    """
    Runs at 09:30 ET every weekday.
    Moves pending orders to active queues.
    """
    from app.queue.order_queue import flush_pending_to_active
    from app.queue.order_worker import mark_and_notify_expired_pending_orders
    from app.notifications.telegram_bot import send_notification

    flush_result = await flush_pending_to_active(market="US", return_expired=True)
    count = int(flush_result.get("moved", 0))
    await mark_and_notify_expired_pending_orders(flush_result.get("expired_orders", []))
    if count > 0:
        await send_notification(
            f"🔔 장이 열렸습니다!\n"
            f"📤 대기 주문 {count}건을 실행 큐로 이동했습니다."
        )
    else:
        logger.info("Market open — no pending orders")

    await job_missed_sell_repair()


async def job_krx_market_open():
    """
    Runs at 09:00 KST every weekday.
    Moves pending orders to active queues; non-KRX orders are rechecked by the worker.
    """
    from app.queue.order_queue import flush_pending_to_active
    from app.queue.order_worker import mark_and_notify_expired_pending_orders
    from app.notifications.telegram_bot import send_notification

    flush_result = await flush_pending_to_active(market="KRX", return_expired=True)
    count = int(flush_result.get("moved", 0))
    await mark_and_notify_expired_pending_orders(flush_result.get("expired_orders", []))
    if count > 0:
        await send_notification(
            f"🔔 한국장이 열렸습니다!\n"
            f"📤 대기 주문 {count}건을 실행 큐로 이동했습니다."
        )
    else:
        logger.info("KRX market open — no pending orders")


async def job_asia_market_open(market: str):
    """
    Moves Asia-market pending orders at each exchange's morning open and
    afternoon restart. This keeps the expanded watchlist responsive even when
    alerts arrive during lunch breaks or before the local market opens.
    """
    from app.queue.order_queue import flush_pending_to_active
    from app.queue.order_worker import mark_and_notify_expired_pending_orders
    from app.notifications.telegram_bot import send_notification

    market_key = str(market or "").strip().upper()
    label = ASIA_MARKET_LABELS.get(market_key, market_key)

    flush_result = await flush_pending_to_active(market=market_key, return_expired=True)
    count = int(flush_result.get("moved", 0))
    await mark_and_notify_expired_pending_orders(flush_result.get("expired_orders", []))
    if count > 0:
        await send_notification(
            f"🔔 {label}이 열렸습니다!\n"
            f"📤 대기 주문 {count}건을 실행 큐로 이동했습니다."
        )
    else:
        logger.info("Asia market open — no pending orders", market=market_key)


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
    from app.database.connection import get_bot_settings, update_bot_setting

    if (settings.broker_mode or "").strip().lower() == "kis_only":
        return

    if not is_market_open():
        return

    result = await sync_positions()
    if result["status"] == "mismatch":
        bot_settings = await get_bot_settings()
        if not bot_settings.is_paused:
            await update_bot_setting("is_paused", True)
            await send_notification(
                "🛑 포지션 불일치가 감지되어 자동으로 매수를 일시중지했습니다.\n"
                "/resume 전에 불일치 원인을 확인해 주세요."
            )
        report = format_sync_report(result)
        await send_notification(report)


async def job_kis_position_reconcile():
    """
    Periodically reconcile KIS real holdings into the local DB.

    This catches ambiguous KIS order states where an order is reported as
    unconfirmed/cancel-failed but later appears in the real account balance.
    """
    if (settings.broker_mode or "").strip().lower() != "kis_only":
        return

    try:
        from sqlalchemy import func, select

        from app.broker.kis_client import get_kis_client
        from app.broker.order_executor import (
            _reconcile_kis_domestic_symbol_to_db,
            _reconcile_kis_symbol_to_db,
        )
        from app.gateway.symbol_mapper import is_kis_domestic_symbol
        from app.database.connection import get_session
        from app.models.position import Position, PositionStatus
        from app.notifications.telegram_bot import send_notification

        kis = await get_kis_client()
        if not kis.is_configured:
            return

        rows = await kis.get_overseas_balance()
        broker_qty: dict[str, float] = {}
        for row in rows:
            symbol = str(
                row.get("ovrs_pdno")
                or row.get("pdno")
                or row.get("item_cd")
                or ""
            ).strip().upper()
            qty = float(
                row.get("ovrs_cblc_qty")
                or row.get("cblc_qty")
                or row.get("hold_qty")
                or row.get("blce_qty")
                or 0.0
            )
            if symbol and qty > 0:
                broker_qty[symbol] = broker_qty.get(symbol, 0.0) + qty

        if settings.kis_domestic_enabled:
            try:
                domestic_rows = await kis.get_domestic_balance()
            except Exception:
                domestic_rows = []
            for row in domestic_rows:
                symbol = str(row.get("pdno") or "").strip().upper()
                qty = float(row.get("hldg_qty") or 0.0)
                if symbol and qty > 0:
                    broker_qty[symbol] = broker_qty.get(symbol, 0.0) + qty

        async with get_session() as session:
            db_rows = (
                await session.execute(
                    select(Position.ticker, func.sum(Position.qty))
                    .where(
                        Position.status == PositionStatus.OPEN,
                        Position.entry_order_id < 0,
                    )
                    .group_by(Position.ticker)
                )
            ).all()

        db_qty = {
            str(symbol or "").strip().upper(): float(qty or 0.0)
            for symbol, qty in db_rows
            if str(symbol or "").strip()
        }
        target_symbols = sorted(set(broker_qty) | set(db_qty))
        mismatches = [
            symbol
            for symbol in target_symbols
            if abs(float(broker_qty.get(symbol, 0.0)) - float(db_qty.get(symbol, 0.0))) > 0.001
        ]
        if not mismatches:
            return

        repaired = []
        errors = []
        for symbol in mismatches:
            try:
                if is_kis_domestic_symbol(symbol):
                    result = await _reconcile_kis_domestic_symbol_to_db(kis, symbol)
                else:
                    result = await _reconcile_kis_symbol_to_db(kis, symbol)
                repaired.append(
                    {
                        "ticker": symbol,
                        "added_qty": float(result.get("added_qty", 0.0) or 0.0),
                        "closed_qty": float(result.get("closed_qty", 0.0) or 0.0),
                        "corporate_action_adjusted": bool(result.get("corporate_action_adjusted")),
                        "split_ratio": str(result.get("split_ratio") or ""),
                        "ok": bool(result.get("ok")),
                    }
                )
                if not result.get("ok"):
                    errors.append(f"{symbol}: {result.get('error', 'unknown')}")
            except Exception as exc:
                errors.append(f"{symbol}: {str(exc)}")

        changed = [
            item
            for item in repaired
            if item["added_qty"] > 0 or item["closed_qty"] > 0 or item.get("corporate_action_adjusted")
        ]
        if changed or errors:
            lines = ["🧭 KIS 보유/DB 자동 정합화"]
            if changed:
                lines.append(
                    "복구: "
                    + ", ".join(
                        (
                            f"{item['ticker']}(분할 {item['split_ratio']})"
                            if item.get("corporate_action_adjusted")
                            else f"{item['ticker']}(+{item['added_qty']:.0f}/-{item['closed_qty']:.0f})"
                        )
                        for item in changed
                    )
                )
            if errors:
                lines.append("확인 필요: " + " | ".join(errors[:5]))
            await send_notification("\n".join(lines))
    except Exception as e:
        logger.error("KIS position reconcile failed", error=str(e))


async def job_sunday_reminder():
    """
    Runs every Sunday at 10:00 ET.
    Reminds to log in to IB Gateway.
    """
    from app.notifications.telegram_bot import send_notification
    if (settings.broker_mode or "").strip().lower() == "kis_only":
        return
    await send_notification(
        "⚠️ 일요일 IB 재인증이 필요합니다!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "월요일 장 시작 전에 IB Gateway에 로그인해 주세요.\n"
        "VPS에 접속해서 인증을 완료해 주세요.\n"
        "\n"
        "⏰ 미국장 개장: 월요일 오전 9:30 (ET)"
    )


async def job_health_check():
    """
    Runs every 5 minutes.
    Checks IB connection and sends alert if disconnected.
    """
    from app.broker.ib_client import get_ib_client
    from app.notifications.telegram_bot import send_notification
    global _last_ib_connected

    if (settings.broker_mode or "").strip().lower() == "kis_only":
        return

    try:
        ib = await get_ib_client()
        current_connected = bool(ib.is_connected)
        if _last_ib_connected is None:
            _last_ib_connected = current_connected
            return

        if not current_connected and _last_ib_connected:
            await send_notification(
                "🔴 IB Gateway 연결이 끊어졌습니다!\n"
                "자동 재연결을 시도 중입니다..."
            )
        elif current_connected and not _last_ib_connected:
            await send_notification("🟢 IB Gateway 연결이 복구되었습니다")

        _last_ib_connected = current_connected
    except Exception as e:
        logger.error("Health check failed", error=str(e))


async def job_site_monitor():
    """
    Runs every 5 minutes.
    Checks site, API, and platform integrity, then reports incidents on change.
    """
    if not settings.site_monitor_enabled:
        return

    try:
        from app.web.site_monitor import run_site_monitor_cycle

        report = await run_site_monitor_cycle(notify=True)
        logger.info(
            "Site monitor completed",
            overall_status=report["overall_status"],
            error_checks=report["error_checks"],
            warning_checks=report["warning_checks"],
        )
    except Exception as e:
        logger.error("Site monitor failed", error=str(e))


async def job_missed_sell_repair():
    """
    Detect failed SELL alerts that still have live KIS holdings and requeue them.
    """
    try:
        from app.trading_safety import repair_missed_sell_orders

        result = await repair_missed_sell_orders(notify=True)
        if result.get("enqueued"):
            logger.warning(
                "Missed SELL repair enqueued orders",
                tickers=[item.get("ticker") for item in result["enqueued"]],
            )
    except Exception as e:
        logger.error("Missed SELL repair failed", error=str(e))


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

    scheduler.add_job(
        job_krx_market_open,
        CronTrigger(hour=9, minute=0, day_of_week="mon-fri", timezone="Asia/Seoul"),
        id="krx_market_open",
        name="KRX Market Open — Flush Pending Queue",
        replace_existing=True,
    )

    for market_key, schedule in ASIA_MARKET_OPEN_SCHEDULES.items():
        timezone = str(schedule["timezone"])
        for hour, minute, session_name in schedule["sessions"]:
            scheduler.add_job(
                job_asia_market_open,
                CronTrigger(
                    hour=hour,
                    minute=minute,
                    day_of_week="mon-fri",
                    timezone=timezone,
                ),
                id=f"{market_key.lower()}_{session_name}_market_open",
                name=f"{market_key} {session_name.title()} Market Open — Flush Pending Queue",
                args=[market_key],
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

    mode = (settings.broker_mode or "").strip().lower()
    if mode != "kis_only":
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
    else:
        logger.info("KIS-only mode: skipped IB-specific scheduler jobs")

    try:
        site_monitor_available = importlib.util.find_spec("app.web.site_monitor") is not None
    except ModuleNotFoundError:
        site_monitor_available = False
    if settings.site_monitor_enabled and site_monitor_available:
        scheduler.add_job(
            job_site_monitor,
            "interval",
            minutes=5,
            id="site_monitor",
            name="Website Incident Monitor",
            replace_existing=True,
        )
    elif settings.site_monitor_enabled and not site_monitor_available:
        logger.warning("Site monitor enabled but app.web.site_monitor is unavailable; skipping")

    scheduler.add_job(
        job_missed_sell_repair,
        "interval",
        minutes=60,
        id="missed_sell_repair",
        name="Missed SELL Auto Repair",
        replace_existing=True,
    )

    if mode == "kis_only":
        scheduler.add_job(
            job_kis_position_reconcile,
            "interval",
            minutes=60,
            id="kis_position_reconcile",
            name="KIS Position DB Reconcile",
            replace_existing=True,
        )

    scheduler.start()
    logger.info("Scheduler started with all jobs")

    return scheduler
