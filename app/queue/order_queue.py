"""
Redis-based order queue with priority handling.
SELL orders get higher priority than BUY orders.
"""

import json
from datetime import datetime, timezone
from typing import Optional
import redis.asyncio as redis
import structlog

from app.config import settings

logger = structlog.get_logger()

# Redis keys
SELL_QUEUE = "orders:sell"    # High priority
BUY_QUEUE = "orders:buy"     # Normal priority
PENDING_QUEUE = "orders:pending"  # Queued for market open
PROCESSING_SET = "orders:processing"  # Currently being processed
IDEMPOTENCY_PREFIX = "orders:idempotency"

_ENQUEUE_ONCE_SCRIPT = """
if redis.call('SET', KEYS[1], ARGV[2], 'NX', 'EX', ARGV[3]) then
    redis.call('LPUSH', KEYS[2], ARGV[1])
    return 1
end
return 0
"""

_redis_client = None


def _queue_name_for_action(action: str) -> str:
    """Return the active Redis queue for an order action."""
    normalized = str(action or "").upper()
    if normalized == "SELL":
        return SELL_QUEUE
    if normalized == "BUY":
        return BUY_QUEUE
    raise ValueError(f"Unknown action, not queued: {action}")


def _idempotency_redis_key(idempotency_key: str) -> str:
    return f"{IDEMPOTENCY_PREFIX}:{idempotency_key}"


def _sanitize_order_for_queue(order_data: dict) -> dict:
    """Remove runtime-only metadata before serializing to Redis."""
    cleaned = dict(order_data)
    cleaned.pop("_queue_source", None)
    cleaned.pop("_raw_queue_payload", None)
    return cleaned


def _deserialize_order(order_json: str, source_queue: str) -> Optional[dict]:
    """Decode Redis payload and attach runtime metadata for ack/requeue."""
    try:
        order = json.loads(order_json)
    except json.JSONDecodeError:
        logger.error("Invalid order payload in queue", payload=order_json)
        return None

    if not isinstance(order, dict):
        logger.error("Unexpected order payload type", payload_type=type(order).__name__)
        return None

    order["_queue_source"] = source_queue
    order["_raw_queue_payload"] = order_json
    return order


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
    order_json = json.dumps(_sanitize_order_for_queue(order_data))

    if action == "SELL":
        await r.lpush(SELL_QUEUE, order_json)
        logger.info("Order queued (SELL priority)", ticker=order_data.get("ticker"))
    elif action == "BUY":
        await r.lpush(BUY_QUEUE, order_json)
        logger.info("Order queued (BUY)", ticker=order_data.get("ticker"))
    else:
        logger.error("Unknown action, not queued", action=action)


async def enqueue_order_once(order_data: dict, *, ttl_seconds: Optional[int] = None) -> bool:
    """
    Enqueue an active order only once per idempotency key.

    TradingView may retry when it times out waiting for a response. The Redis
    script makes the dedupe marker and LPUSH atomic, so a retry cannot create a
    second order if the first one was actually accepted.
    """
    r = await get_redis()
    queue_name = _queue_name_for_action(order_data.get("action", ""))
    order_json = json.dumps(_sanitize_order_for_queue(order_data))
    idempotency_key = str(order_data.get("idempotency_key") or "").strip()

    if not idempotency_key:
        await r.lpush(queue_name, order_json)
        logger.info(
            "Order queued without idempotency key",
            ticker=order_data.get("ticker"),
            action=order_data.get("action"),
        )
        return True

    ttl = int(ttl_seconds or settings.webhook_idempotency_ttl_seconds)
    ttl = max(ttl, 60)
    result = await r.eval(
        _ENQUEUE_ONCE_SCRIPT,
        2,
        _idempotency_redis_key(idempotency_key),
        queue_name,
        order_json,
        datetime.now(timezone.utc).isoformat(),
        ttl,
    )
    queued = int(result or 0) == 1
    if queued:
        logger.info(
            "Order queued with idempotency guard",
            ticker=order_data.get("ticker"),
            action=order_data.get("action"),
        )
    else:
        logger.warning(
            "Duplicate order ignored by Redis idempotency guard",
            ticker=order_data.get("ticker"),
            action=order_data.get("action"),
            idempotency_key=idempotency_key,
        )
    return queued


async def enqueue_pending(order_data: dict):
    """
    Queue an order for execution at market open.
    Used when alerts arrive outside market hours.
    """
    r = await get_redis()
    payload = _sanitize_order_for_queue(order_data)
    payload["queued_at"] = datetime.now(timezone.utc).isoformat()
    payload["pending_reason"] = "outside_market_hours"
    order_json = json.dumps(payload)
    await r.lpush(PENDING_QUEUE, order_json)
    logger.info(
        "Order queued for market open",
        ticker=order_data.get("ticker"),
        action=order_data.get("action"),
    )


async def dequeue_order() -> Optional[dict]:
    """
    Get next order to process.
    Priority: SELL queue first, then BUY queue.
    """
    r = await get_redis()

    # Use atomic move to processing queue for crash safety.
    order_json = await r.rpoplpush(SELL_QUEUE, PROCESSING_SET)
    if order_json:
        order = _deserialize_order(order_json, SELL_QUEUE)
        if order is not None:
            return order
        await r.lrem(PROCESSING_SET, 1, order_json)

    order_json = await r.rpoplpush(BUY_QUEUE, PROCESSING_SET)
    if order_json:
        order = _deserialize_order(order_json, BUY_QUEUE)
        if order is not None:
            return order
        await r.lrem(PROCESSING_SET, 1, order_json)

    return None


async def ack_processed_order(order_data: dict):
    """Acknowledge completion by removing payload from processing queue."""
    raw_payload = order_data.get("_raw_queue_payload")
    if not raw_payload:
        return

    r = await get_redis()
    await r.lrem(PROCESSING_SET, 1, raw_payload)


async def requeue_inflight_orders() -> int:
    """
    Move any in-flight orders back to active queues on worker startup.
    Prevents order loss after worker crash/restart.
    """
    r = await get_redis()
    moved = 0

    while True:
        order_json = await r.rpop(PROCESSING_SET)
        if not order_json:
            break

        try:
            order = json.loads(order_json)
        except json.JSONDecodeError:
            logger.error("Dropping invalid payload from processing queue", payload=order_json)
            continue

        action = str(order.get("action", "")).upper()
        if action == "SELL":
            await r.lpush(SELL_QUEUE, order_json)
        elif action == "BUY":
            await r.lpush(BUY_QUEUE, order_json)
        else:
            logger.error("Dropping unknown action from processing queue", action=action)
            continue

        moved += 1

    if moved > 0:
        logger.warning("Recovered in-flight orders after restart", count=moved)
    return moved


async def requeue_processing_order(order_data: dict) -> bool:
    """
    Move a specific processing payload back to its source queue.
    Used when retry-queue insertion fails while handling an exception.
    """
    raw_payload = order_data.get("_raw_queue_payload")
    source_queue = order_data.get("_queue_source")
    if not raw_payload or source_queue not in (SELL_QUEUE, BUY_QUEUE):
        return False

    r = await get_redis()
    pipe = r.pipeline(transaction=True)
    pipe.lrem(PROCESSING_SET, 1, raw_payload)
    pipe.lpush(source_queue, raw_payload)
    await pipe.execute()
    return True


def _pending_order_matches_market(order_data: dict, market: Optional[str]) -> bool:
    """Return whether a pending order should wake for the requested market."""
    if not market:
        return True

    from app.broker.market_hours import ASIA_MARKET_SESSIONS
    from app.gateway.symbol_mapper import is_kis_domestic_symbol, split_tv_ticker

    ticker = str(order_data.get("ticker", "") or "")
    market_upper = str(market or "").strip().upper()
    exchange, _ = split_tv_ticker(ticker)
    is_domestic = is_kis_domestic_symbol(ticker)
    if market_upper == "KRX":
        return is_domestic
    if market_upper in ASIA_MARKET_SESSIONS:
        return exchange == market_upper
    if market_upper in ("US", "USA"):
        return not is_domestic and exchange not in ASIA_MARKET_SESSIONS
    return True


def _parse_order_datetime(value) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def pending_order_age_hours(order_data: dict, now_utc: Optional[datetime] = None) -> Optional[float]:
    """Return pending order age from queued/received timestamp."""
    now = now_utc or datetime.now(timezone.utc)
    queued_at = (
        _parse_order_datetime(order_data.get("queued_at"))
        or _parse_order_datetime(order_data.get("received_at"))
        or _parse_order_datetime(order_data.get("created_at"))
    )
    if queued_at is None:
        return None
    return max(0.0, (now - queued_at).total_seconds() / 3600.0)


def is_pending_order_expired(order_data: dict, now_utc: Optional[datetime] = None) -> bool:
    """Return True when a market-open pending order is too old for the 4h/4h strategy."""
    ttl_hours = float(settings.pending_order_ttl_hours or 0.0)
    if ttl_hours <= 0:
        return False
    age_hours = pending_order_age_hours(order_data, now_utc=now_utc)
    return age_hours is not None and age_hours > ttl_hours


async def purge_expired_pending_orders(now_utc: Optional[datetime] = None) -> list[dict]:
    """
    Remove expired pending orders and return their decoded payloads.

    The caller is responsible for marking AlertLog rows and sending operator
    notifications because this queue module should stay broker/UI agnostic.
    """
    r = await get_redis()
    expired: list[dict] = []
    kept = 0
    now = now_utc or datetime.now(timezone.utc)
    pending_count = await r.llen(PENDING_QUEUE)

    for _ in range(pending_count):
        order_json = await r.rpop(PENDING_QUEUE)
        if not order_json:
            break

        try:
            order_data = json.loads(order_json)
        except json.JSONDecodeError:
            logger.error("Dropping invalid pending order payload", payload=order_json)
            continue

        if is_pending_order_expired(order_data, now_utc=now):
            expired.append(order_data)
            continue

        await r.lpush(PENDING_QUEUE, order_json)
        kept += 1

    if expired:
        logger.warning(
            "Purged expired pending orders",
            expired=len(expired),
            kept=kept,
            ttl_hours=settings.pending_order_ttl_hours,
        )
    return expired


async def flush_pending_to_active(market: Optional[str] = None):
    """
    Move pending orders (waiting for market open) to active queues.
    Called by scheduler at market open.

    If market is provided, only matching orders are moved. Non-matching orders
    stay pending so KRX and US sessions do not wake each other's orders.
    """
    r = await get_redis()
    count = 0
    kept = 0
    expired = 0
    now = datetime.now(timezone.utc)

    pending_count = await r.llen(PENDING_QUEUE)
    for _ in range(pending_count):
        order_json = await r.rpop(PENDING_QUEUE)
        if not order_json:
            break

        try:
            order_data = json.loads(order_json)
        except json.JSONDecodeError:
            logger.error("Dropping invalid pending order payload", payload=order_json)
            continue

        if is_pending_order_expired(order_data, now_utc=now):
            expired += 1
            continue

        if not _pending_order_matches_market(order_data, market):
            await r.lpush(PENDING_QUEUE, order_json)
            kept += 1
            continue

        action = order_data.get("action", "").upper()

        if action == "SELL":
            await r.lpush(SELL_QUEUE, order_json)
        else:
            await r.lpush(BUY_QUEUE, order_json)

        count += 1

    if count > 0 or expired > 0:
        logger.info(
            "Moved pending orders to active queues",
            count=count,
            kept=kept,
            expired=expired,
            market=market or "ALL",
        )

    return count


async def get_queue_stats() -> dict:
    """Get current queue sizes for monitoring."""
    r = await get_redis()

    sell_size = await r.llen(SELL_QUEUE)
    buy_size = await r.llen(BUY_QUEUE)
    pending_size = await r.llen(PENDING_QUEUE)
    processing_size = await r.llen(PROCESSING_SET)
    pending_krx = 0
    pending_us = 0
    pending_asia = 0
    pending_unknown = 0
    pending_expired = 0
    now = datetime.now(timezone.utc)

    for order_json in await r.lrange(PENDING_QUEUE, 0, -1):
        try:
            order_data = json.loads(order_json)
        except json.JSONDecodeError:
            pending_unknown += 1
            continue

        if is_pending_order_expired(order_data, now_utc=now):
            pending_expired += 1

        if _pending_order_matches_market(order_data, "KRX"):
            pending_krx += 1
        elif any(_pending_order_matches_market(order_data, market) for market in ("HKEX", "SSE", "SZSE", "TSE")):
            pending_asia += 1
        elif _pending_order_matches_market(order_data, "US"):
            pending_us += 1
        else:
            pending_unknown += 1

    return {
        "sell_queue": sell_size,
        "buy_queue": buy_size,
        "pending_queue": pending_size,
        "pending_krx": pending_krx,
        "pending_us": pending_us,
        "pending_asia": pending_asia,
        "pending_unknown": pending_unknown,
        "pending_expired": pending_expired,
        "processing_queue": processing_size,
        "total": sell_size + buy_size + pending_size + processing_size,
    }


async def get_waiting_ticker_stats(include_processing: bool = False) -> dict:
    """
    Aggregate waiting BUY/SELL queue items by order count and unique ticker count.
    Waiting queues include sell/buy/pending, and optionally processing queue.
    """
    r = await get_redis()
    queue_names = [SELL_QUEUE, BUY_QUEUE, PENDING_QUEUE]
    if include_processing:
        queue_names.append(PROCESSING_SET)

    buy_orders = 0
    sell_orders = 0
    buy_tickers: set[str] = set()
    sell_tickers: set[str] = set()
    invalid_payloads = 0

    for queue_name in queue_names:
        rows = await r.lrange(queue_name, 0, -1)
        for raw in rows:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                invalid_payloads += 1
                continue

            if not isinstance(payload, dict):
                invalid_payloads += 1
                continue

            action = str(payload.get("action", "")).upper().strip()
            ticker = str(payload.get("ticker", "")).upper().strip()

            if action == "BUY":
                buy_orders += 1
                if ticker:
                    buy_tickers.add(ticker)
            elif action == "SELL":
                sell_orders += 1
                if ticker:
                    sell_tickers.add(ticker)

    return {
        "buy_order_count": buy_orders,
        "sell_order_count": sell_orders,
        "buy_ticker_count": len(buy_tickers),
        "sell_ticker_count": len(sell_tickers),
        "invalid_payload_count": invalid_payloads,
    }


async def get_waiting_buy_orders(include_processing: bool = False) -> list[dict]:
    """Return waiting BUY order payloads for cash coverage checks."""
    r = await get_redis()
    queue_names = [BUY_QUEUE, PENDING_QUEUE]
    if include_processing:
        queue_names.append(PROCESSING_SET)

    orders: list[dict] = []
    for queue_name in queue_names:
        rows = await r.lrange(queue_name, 0, -1)
        for raw in rows:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("action", "")).upper().strip() != "BUY":
                continue

            item = dict(payload)
            item["_queue_source"] = queue_name
            orders.append(item)

    return orders


async def clear_all_queues():
    """Clear all order queues (emergency use)."""
    r = await get_redis()
    await r.delete(SELL_QUEUE, BUY_QUEUE, PENDING_QUEUE, PROCESSING_SET)
    logger.warning("All order queues cleared")
