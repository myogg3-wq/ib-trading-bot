"""
FastAPI Webhook endpoint.
Receives TradingView alerts, validates, and pushes to Redis order queue.
"""

import json
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
import structlog

from app.gateway.security import validate_webhook_request, verify_payload_secret
from app.gateway.symbol_mapper import validate_ticker
from app.database.connection import get_session
from app.models.alert_log import AlertLog
from app.queue.order_queue import enqueue_order

logger = structlog.get_logger()

router = APIRouter()


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
    # 1. Validate request (IP whitelist, body)
    body = await validate_webhook_request(request)

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

    if action not in ("BUY", "SELL"):
        logger.error("Invalid action", action=action)
        raise HTTPException(status_code=400, detail="Invalid action. Must be BUY or SELL")

    if not validate_ticker(ticker):
        logger.error("Invalid ticker", ticker=ticker)
        raise HTTPException(status_code=400, detail="Invalid ticker")

    # Parse price if provided
    try:
        price_float = float(price) if price else None
    except (ValueError, TypeError):
        price_float = None

    # 5. Build idempotency key
    idempotency_key = alert_id or f"{action}_{ticker}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    # 6. Log alert to DB
    async with get_session() as session:
        # Check idempotency (skip duplicate alerts)
        if alert_id:
            from sqlalchemy import select
            existing = await session.execute(
                select(AlertLog).where(AlertLog.idempotency_key == idempotency_key)
            )
            if existing.scalar_one_or_none():
                logger.warning("Duplicate alert, skipping", alert_id=alert_id, ticker=ticker)
                return {"status": "duplicate", "message": "Alert already processed"}

        alert_log = AlertLog(
            ticker=ticker,
            action=action,
            price=price_float,
            alert_id=alert_id,
            raw_payload=json.dumps(payload),
            source_ip=request.client.host if request.client else "unknown",
            idempotency_key=idempotency_key,
            received_at=datetime.now(timezone.utc),
        )
        session.add(alert_log)

    # 7. Push to order queue
    order_data = {
        "action": action,
        "ticker": ticker,
        "price": price_float,
        "alert_id": alert_id,
        "idempotency_key": idempotency_key,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

    await enqueue_order(order_data)

    logger.info(
        "Alert received and queued",
        action=action,
        ticker=ticker,
        price=price_float,
    )

    # 8. Return 202 Accepted (processing async)
    return {
        "status": "accepted",
        "action": action,
        "ticker": ticker,
    }


@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ib-trading-bot",
    }
