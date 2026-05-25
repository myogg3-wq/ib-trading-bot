"""
FastAPI Webhook endpoint.
Receives TradingView alerts, validates, and pushes to Redis order queue.
"""

import json
import hashlib
import asyncio
from time import perf_counter
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.gateway.security import (
    validate_webhook_request,
    verify_payload_secret,
    check_timestamp_freshness,
)
from app.gateway.symbol_mapper import validate_ticker, parse_tv_ticker, canonical_trade_symbol
from app.database.connection import get_session, get_bot_settings
from app.models.alert_log import AlertLog
from app.models.position import Position, PositionStatus
from app.queue.order_queue import enqueue_order_once
from app.notifications.telegram_bot import send_notification
from app.broker.market_hours import is_market_open

logger = structlog.get_logger()

router = APIRouter()


async def _persist_queued_alert_log(
    *,
    ticker: str,
    action: str,
    price: Optional[float],
    alert_id: str,
    raw_payload: str,
    source_ip: str,
    idempotency_key: str,
    received_at: datetime,
) -> None:
    """Persist webhook audit data without delaying TradingView's response."""
    try:
        async with get_session() as session:
            existing = (
                await session.execute(
                    select(AlertLog)
                    .where(AlertLog.idempotency_key == idempotency_key)
                    .limit(1)
                )
            ).scalar_one_or_none()

            if existing:
                if not existing.processed:
                    existing.queued = True
                    existing.skipped = False
                    existing.skip_reason = None
                if not existing.raw_payload:
                    existing.raw_payload = raw_payload
                if not existing.source_ip:
                    existing.source_ip = source_ip
                return

            session.add(
                AlertLog(
                    ticker=ticker,
                    action=action,
                    price=price,
                    alert_id=alert_id,
                    raw_payload=raw_payload,
                    source_ip=source_ip,
                    idempotency_key=idempotency_key,
                    received_at=received_at,
                    queued=True,
                    processed=False,
                    skipped=False,
                )
            )
    except IntegrityError:
        logger.info(
            "Alert log already exists after concurrent webhook processing",
            ticker=ticker,
            action=action,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        logger.warning(
            "Background alert-log persistence failed",
            ticker=ticker,
            action=action,
            idempotency_key=idempotency_key,
            error=str(exc),
        )


def _persist_queued_alert_log_in_background(**kwargs) -> None:
    async def _runner() -> None:
        await _persist_queued_alert_log(**kwargs)

    asyncio.create_task(_runner())


def _notify_received_alert_in_background(
    *,
    action: str,
    ticker: str,
    price_float: Optional[float],
    alert_id: str,
    alert_time: str,
    idempotency_key: str,
) -> None:
    """Evaluate verbose notification policy outside the webhook response path."""
    async def _runner() -> None:
        try:
            if await _should_send_received_alert_notification():
                await send_notification(
                    _format_received_alert_message(
                        action=action,
                        ticker=ticker,
                        price_float=price_float,
                        alert_id=alert_id,
                        alert_time=alert_time,
                        idempotency_key=idempotency_key,
                    )
                )
        except Exception as exc:
            logger.warning("Background received-alert notify failed", error=str(exc))

    asyncio.create_task(_runner())


def _format_received_alert_message(
    action: str,
    ticker: str,
    price_float: Optional[float],
    alert_id: str,
    alert_time: str,
    idempotency_key: str,
) -> str:
    """Format a Telegram message for an accepted TradingView alert."""
    price_text = f"${price_float:.2f}" if price_float is not None else "-"
    return (
        f"📡 트레이딩뷰 알림 수신\n"
        f"종목: {ticker}\n"
        f"동작: {action}\n"
        f"가격: {price_text}\n"
        f"TV 시간: {alert_time or '-'}\n"
        f"알림 ID: {alert_id or '-'}\n"
        f"추적키: {idempotency_key[:12]}...\n"
        f"상태: 주문 큐 등록 완료"
    )


async def _should_send_received_alert_notification() -> bool:
    """
    Hide routine webhook intake messages by default.

    Telegram should stay operator-friendly: fills, failures, risk blocks, pending
    summaries, and reports are useful; "alert received / queued" is mostly a
    debug message and becomes noisy with large TradingView watchlists.
    """
    if not settings.telegram_verbose_webhook_alerts:
        return False

    if is_market_open():
        return True

    try:
        bot_settings = await get_bot_settings()
    except Exception as exc:
        logger.warning("Failed to load bot settings for webhook notify policy", error=str(exc))
        return True

    if bot_settings.regular_hours_only and bot_settings.queue_outside_hours:
        return False
    return True


async def _has_open_position(symbol: str) -> bool:
    """Return True when a symbol is currently held in the local position ledger."""
    async with get_session() as session:
        result = await session.execute(
            select(Position.id)
            .where(Position.ticker == symbol, Position.status == PositionStatus.OPEN)
            .limit(1)
        )
        return result.first() is not None


@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Receive TradingView webhook alert.

    Expected JSON payload:
    {
        "secret": "your_webhook_secret",
        "action": "BUY" or "SELL",
        "ticker": "AAPL" or "NASDAQ:AAPL",
        "price": "150.25",         (optional, for logging)
        "time": "{{timenow}}",     (optional)
        "alert_id": "unique_id"    (optional, for idempotency)
    }
    """
    started_at = perf_counter()

    # 1. Validate request (IP whitelist, body)
    body = await validate_webhook_request(request)
    source_ip = request.client.host if request.client else "unknown"

    # 2. Parse JSON
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 3. Verify secret in payload
    if not verify_payload_secret(payload):
        logger.warning("Invalid secret in payload")
        raise HTTPException(status_code=401, detail="Invalid secret")

    # 4. Extract and validate fields
    action = payload.get("action", "").upper().strip()
    ticker = payload.get("ticker", "").strip()
    price = payload.get("price")
    alert_id = payload.get("alert_id", "")
    alert_time = str(payload.get("time", "")).strip()

    if action not in ("BUY", "SELL"):
        logger.error("Invalid action", action=action)
        raise HTTPException(status_code=400, detail="Invalid action. Must be BUY or SELL")

    if not validate_ticker(ticker):
        logger.error("Invalid ticker", ticker=ticker)
        raise HTTPException(status_code=400, detail="Invalid ticker")

    raw_ticker = ticker.strip().upper()
    symbol = parse_tv_ticker(ticker)["symbol"].upper()
    trade_symbol = canonical_trade_symbol(ticker).upper()
    allowed = set(settings.allowed_ticker_list)
    if allowed and trade_symbol not in allowed and symbol not in allowed and raw_ticker not in allowed:
        if (
            action == "SELL"
            and settings.allow_sell_for_open_positions_outside_allowlist
            and await _has_open_position(trade_symbol)
        ):
            logger.info(
                "Out-of-allowlist SELL accepted for existing open position",
                ticker=ticker,
                symbol=trade_symbol,
                action=action,
            )
        else:
            logger.warning(
                "Ticker not in allowlist, ignoring alert",
                ticker=ticker,
                symbol=trade_symbol,
                action=action,
            )
            return {
                "status": "ignored",
                "reason": "ticker_not_allowed",
                "ticker": ticker,
            }

    # Parse price if provided
    try:
        price_float = float(price) if price else None
    except (ValueError, TypeError):
        price_float = None

    # 5. Check replay freshness when timestamp exists
    if alert_time and not check_timestamp_freshness(alert_time, max_age_seconds=300):
        logger.warning(
            "Stale alert rejected",
            ticker=ticker,
            action=action,
            alert_time=alert_time,
            source_ip=source_ip,
        )
        raise HTTPException(status_code=400, detail="Stale alert")

    # 6. Build idempotency key
    payload_fingerprint = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload_fingerprint.encode("utf-8")).hexdigest()
    if alert_id:
        # Do not rely on alert_id alone (can collide across symbols/actions).
        raw_key = f"aid|{alert_id}|{action}|{trade_symbol}|{alert_time}|{payload_hash}"
    else:
        time_token = alert_time or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        raw_key = (
            f"payload|{action}|{trade_symbol}|{time_token}|"
            f"{price_float if price_float is not None else ''}|{payload_hash}"
        )
    idempotency_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    now_utc = datetime.now(timezone.utc)

    # 7. Push to order queue first. TradingView marks webhooks failed if the
    # receiver does not respond quickly, so DB audit writes happen after ACK.
    order_data = {
        "action": action,
        "ticker": trade_symbol,
        "price": price_float,
        "alert_id": alert_id,
        "idempotency_key": idempotency_key,
        "retry_count": 0,
        "received_at": now_utc.isoformat(),
        "source_ip": source_ip,
    }

    try:
        enqueue_timeout = max(0.2, float(settings.webhook_enqueue_timeout_seconds))
        queued = await asyncio.wait_for(
            enqueue_order_once(
                order_data,
                ttl_seconds=settings.webhook_idempotency_ttl_seconds,
            ),
            timeout=enqueue_timeout,
        )
    except asyncio.TimeoutError:
        logger.error(
            "Queue enqueue timed out",
            action=action,
            ticker=trade_symbol,
            idempotency_key=idempotency_key,
            timeout_seconds=settings.webhook_enqueue_timeout_seconds,
        )
        raise HTTPException(status_code=503, detail="Queue timeout, retry later")
    except Exception as exc:
        logger.error(
            "Queue enqueue failed",
            action=action,
            ticker=trade_symbol,
            idempotency_key=idempotency_key,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Queue unavailable, retry later")

    latency_ms = int((perf_counter() - started_at) * 1000)

    if not queued:
        logger.warning(
            "Duplicate alert skipped before enqueue",
            alert_id=alert_id,
            ticker=trade_symbol,
            idempotency_key=idempotency_key,
            latency_ms=latency_ms,
        )
        return {"status": "duplicate", "message": "Alert already queued"}

    _persist_queued_alert_log_in_background(
        ticker=trade_symbol,
        action=action,
        price=price_float,
        alert_id=alert_id,
        raw_payload=payload_fingerprint,
        source_ip=source_ip,
        idempotency_key=idempotency_key,
        received_at=now_utc,
    )
    latency_ms = int((perf_counter() - started_at) * 1000)

    logger.info(
        "Alert received and queued",
        action=action,
        ticker=trade_symbol,
        price=price_float,
        idempotency_key=idempotency_key,
        latency_ms=latency_ms,
    )
    if latency_ms >= settings.webhook_slow_request_ms:
        logger.warning(
            "Slow webhook request observed",
            action=action,
            ticker=trade_symbol,
            idempotency_key=idempotency_key,
            latency_ms=latency_ms,
        )
    _notify_received_alert_in_background(
        action=action,
        ticker=trade_symbol,
        price_float=price_float,
        alert_id=alert_id,
        alert_time=alert_time,
        idempotency_key=idempotency_key,
    )

    # 8. Return 202 Accepted (processing async)
    return {
        "status": "accepted",
        "action": action,
        "ticker": trade_symbol,
    }


@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ib-trading-bot",
    }
