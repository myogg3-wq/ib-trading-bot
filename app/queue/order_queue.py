"""
Redis-based order queue with priority handling.
SELL orders get higher priority than BUY orders.
"""

import json
from datetime import datetime, timezone
import redis.asyncio as redis
import structlog

from app.config import settings

logger = structlog.get_logger()

# Redis keys
SELL_QUEUE = "orders:sell"    # High priority
BUY_QUEUE = "orders:buy"     # Normal priority
PENDING_QUEUE = "orders:pending"  # Queued for market open
PROCESSING_SET = "orders:processing"  # Currently being processed

_redis_client = None


async def get_redis() -> redis.Redis:
    """Get Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_client


async def enqueue_order(order_data: dict):
    """
    Push an order to the appropriate Redis queue.
    SELL → high priority queue
    BUY → normal priority queue
    """
    r = await get_redis()
    action = order_data.get("action", "").upper()
    order_json = json.dumps(order_data)

    if action == "SELL":
        await r.lpush(SELL_QUEUE, order_json)
        logger.info("Order queued (SELL priority)", ticker=order_data.get("ticker"))
    elif action == "BUY":
        await r.lpush(BUY_QUEUE, order_json)
        logger.info("Order queued (BUY)", ticker=order_data.get("ticker"))
    else:
        logger.error("Unknown action, not queued", action=action)


async def enqueue_pending(order_data: dict):
    """
    Queue an order for execution at market open.
    Used when alerts arrive outside market hours.
    """
    r = await get_redis()
    order_data["queued_at"] = datetime.now(timezone.utc).isoformat()
    order_data["pending_reason"] = "outside_market_hours"
    order_json = json.dumps(order_data)
    await r.lpush(PENDING_QUEUE, order_json)
    logger.info(
        "Order queued for market open",
        ticker=order_data.get("ticker"),
        action=order_data.get("action"),
    )


async def dequeue_order() -> dict | None:
    """
    Get next order to process.
    Priority: SELL queue first, then BUY queue.
    """
    r = await get_redis()

    # Check SELL queue first (higher priority)
    order_json = await r.rpop(SELL_QUEUE)
    if order_json:
        return json.loads(order_json)

    # Then BUY queue
    order_json = await r.rpop(BUY_QUEUE)
    if order_json:
        return json.loads(order_json)

    return None


async def flush_pending_to_active():
    """
    Move all pending orders (waiting for market open) to active queues.
    Called by scheduler at market open.
    """
    r = await get_redis()
    count = 0

    while True:
        order_json = await r.rpop(PENDING_QUEUE)
        if not order_json:
            break

        order_data = json.loads(order_json)
        action = order_data.get("action", "").upper()

        if action == "SELL":
            await r.lpush(SELL_QUEUE, order_json)
        else:
            await r.lpush(BUY_QUEUE, order_json)

        count += 1

    if count > 0:
        logger.info(f"Moved {count} pending orders to active queues")

    return count


async def get_queue_stats() -> dict:
    """Get current queue sizes for monitoring."""
    r = await get_redis()

    sell_size = await r.llen(SELL_QUEUE)
    buy_size = await r.llen(BUY_QUEUE)
    pending_size = await r.llen(PENDING_QUEUE)

    return {
        "sell_queue": sell_size,
        "buy_queue": buy_size,
        "pending_queue": pending_size,
        "total": sell_size + buy_size + pending_size,
    }


async def clear_all_queues():
    """Clear all order queues (emergency use)."""
    r = await get_redis()
    await r.delete(SELL_QUEUE, BUY_QUEUE, PENDING_QUEUE, PROCESSING_SET)
    logger.warning("All order queues cleared")
