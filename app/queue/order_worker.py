"""
Order queue worker.
Continuously processes orders from Redis queues with rate limiting.
Handles market hours, risk checks, and order execution.
"""

import asyncio
import signal
import sys
from datetime import datetime, timezone
import structlog

from app.config import settings
from app.database.connection import init_db, get_bot_settings
from app.queue.order_queue import dequeue_order, enqueue_pending, get_queue_stats
from app.broker.ib_client import get_ib_client
from app.broker.market_hours import is_market_open, get_market_status
from app.broker.order_executor import execute_buy, execute_sell
from app.risk.risk_manager import check_all_buy_risks, check_sell_risks
from app.notifications.telegram_bot import send_notification

logger = structlog.get_logger()

# Rate limiting
_last_order_time = 0.0
_min_order_interval = 1.0 / settings.max_orders_per_second  # seconds between orders


async def rate_limit():
    """Enforce rate limiting between orders."""
    global _last_order_time
    now = asyncio.get_event_loop().time()
    elapsed = now - _last_order_time

    if elapsed < _min_order_interval:
        await asyncio.sleep(_min_order_interval - elapsed)

    _last_order_time = asyncio.get_event_loop().time()


async def process_order(order_data: dict) -> dict:
    """
    Process a single order from the queue.

    Flow:
    1. Check market hours → queue for later if closed
    2. Check risk limits → skip if exceeded
    3. Execute order via IB
    4. Send Telegram notification
    """
    action = order_data.get("action", "").upper()
    ticker = order_data.get("ticker", "")
    alert_id = order_data.get("alert_id", "")

    logger.info("Processing order", action=action, ticker=ticker)

    # 1. Check market hours
    bot_settings = await get_bot_settings()

    if bot_settings.regular_hours_only and not is_market_open():
        if bot_settings.queue_outside_hours:
            await enqueue_pending(order_data)
            market = get_market_status()
            msg = (
                f"⏳ {action} {ticker} queued for market open\n"
                f"Market: {market['emoji']} {market['status']}\n"
                f"Next open: {market['next_open_in']}"
            )
            await send_notification(msg)
            return {"status": "pending", "reason": "outside_market_hours"}
        else:
            msg = f"⏭️ {action} {ticker} skipped (market closed)"
            await send_notification(msg)
            return {"status": "skipped", "reason": "market_closed"}

    # 2. Risk checks
    if action == "BUY":
        risk_result = await check_all_buy_risks(ticker)
        if risk_result is False:  # Risk check failed
            msg = f"⚠️ BUY {ticker} blocked by risk check"
            await send_notification(msg)
            return {"status": "blocked", "reason": "risk_check_failed"}
    elif action == "SELL":
        risk_result = await check_sell_risks()
        if risk_result is False:  # Risk check failed
            msg = f"⚠️ SELL {ticker} blocked by risk check"
            await send_notification(msg)
            return {"status": "blocked", "reason": "risk_check_failed"}

    # 3. Rate limit
    await rate_limit()

    # 4. Execute order
    try:
        if action == "BUY":
            result = await execute_buy(ticker, alert_id)
        elif action == "SELL":
            result = await execute_sell(ticker, alert_id)
        else:
            return {"status": "error", "reason": f"Unknown action: {action}"}
    except Exception as e:
        error_msg = f"❌ {action} {ticker} failed: {str(e)}"
        logger.error("Order execution failed", action=action, ticker=ticker, error=str(e))
        await send_notification(error_msg)
        return {"status": "error", "reason": str(e)}

    # 5. Send notification
    if result.get("success"):
        if action == "BUY":
            msg = (
                f"📈 BUY {result['ticker']}\n"
                f"Qty: {result['qty']} × ${result['price']:.2f}\n"
                f"Amount: ${result['amount']:.2f}\n"
                f"Commission: ${result.get('commission', 0):.2f}"
            )
        else:  # SELL
            pnl = result['pnl']
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            msg = (
                f"📉 SELL {result['ticker']} (ALL {result['positions_closed']} positions)\n"
                f"Qty: {result['qty']} × ${result['price']:.2f}\n"
                f"Entry total: ${result['entry_total']:.2f}\n"
                f"Exit total: ${result['exit_total']:.2f}\n"
                f"{pnl_emoji} PnL: ${pnl:+.2f} ({result['pnl_pct']:+.1f}%)"
            )
    else:
        msg = f"❌ {action} {ticker} failed: {result.get('error', 'Unknown error')}"

    await send_notification(msg)
    return result


async def worker_loop():
    """
    Main worker loop.
    Continuously polls Redis queues and processes orders.
    """
    logger.info("Order worker starting...")

    # Initialize DB
    await init_db()

    # Connect to IB Gateway
    try:
        ib = await get_ib_client()
        if ib.is_connected:
            logger.info("Worker connected to IB Gateway")
            await send_notification("🟢 Trading bot worker started and connected to IB Gateway")
        else:
            logger.warning("Worker could not connect to IB Gateway, will retry...")
            await send_notification("🟡 Trading bot worker started but IB Gateway not connected")
    except Exception as e:
        logger.warning(f"IB Gateway connection failed: {e}, will retry...")
        await send_notification(f"🟡 Trading bot worker started, IB connection pending: {str(e)}")

    # Main processing loop
    empty_count = 0
    while True:
        try:
            order = await dequeue_order()

            if order is None:
                # No orders in queue, wait and check again
                empty_count += 1
                # Progressive backoff: 0.1s → 0.5s → 1s → 2s max
                wait_time = min(0.1 * (2 ** min(empty_count, 4)), 2.0)
                await asyncio.sleep(wait_time)
                continue

            empty_count = 0
            await process_order(order)

        except Exception as e:
            logger.error("Worker loop error", error=str(e))
            await asyncio.sleep(5)  # Wait before retrying


def handle_shutdown(signum, frame):
    """Handle graceful shutdown."""
    logger.info("Shutdown signal received, stopping worker...")
    sys.exit(0)


if __name__ == "__main__":
    # Handle signals for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    asyncio.run(worker_loop())
