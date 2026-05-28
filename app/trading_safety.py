"""
Trading safety checks and repair helpers.

The main purpose is to catch a SELL signal that was received but did not
successfully close an existing KIS position because of a transient broker error.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select

from app.broker.kis_client import get_kis_client
from app.broker.market_hours import is_market_open_for_ticker
from app.database.connection import get_session
from app.gateway.symbol_mapper import is_kis_domestic_symbol
from app.models.alert_log import AlertLog
from app.models.position import Position, PositionStatus
from app.queue.order_queue import enqueue_order, enqueue_pending

logger = structlog.get_logger()

NO_POSITION_REASONS = {
    "no_open_position",
    "보유 포지션 없음: 대기 매도 정리",
}

INTENTIONAL_SELL_HOLD_REASONS = {
    "sell_profit_only_hold",
    "sell_profit_check_failed",
    "corporate_action_review_required",
}


def _normalize_ticker(value: str) -> str:
    return str(value or "").strip().upper()


async def find_missed_sell_candidates() -> list[dict[str, Any]]:
    """
    Return open DB positions that had a failed/skipped SELL alert after entry.

    This is intentionally conservative:
    - no-position skips are ignored
    - already queued repair SELLs are ignored
    - KIS balance is checked before returning a candidate
    """
    async with get_session() as session:
        open_rows = (
            await session.execute(
                select(
                    Position.ticker,
                    func.min(Position.entry_time).label("earliest_entry"),
                    func.sum(Position.qty).label("db_qty"),
                )
                .where(Position.status == PositionStatus.OPEN)
                .group_by(Position.ticker)
            )
        ).all()

        candidates: list[dict[str, Any]] = []
        for ticker, earliest_entry, db_qty in open_rows:
            symbol = _normalize_ticker(ticker)
            if not symbol or not earliest_entry:
                continue

            failed_sell = (
                await session.execute(
                    select(AlertLog)
                    .where(
                        AlertLog.ticker == symbol,
                        AlertLog.action == "SELL",
                        AlertLog.received_at >= earliest_entry,
                        AlertLog.skipped.is_(True),
                    )
                    .order_by(AlertLog.received_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not failed_sell:
                continue

            reason = str(failed_sell.skip_reason or "").strip()
            if reason in NO_POSITION_REASONS:
                continue
            if reason in INTENTIONAL_SELL_HOLD_REASONS:
                continue

            already_queued = (
                (
                    await session.execute(
                        select(func.count(AlertLog.id)).where(
                            AlertLog.ticker == symbol,
                            AlertLog.action == "SELL",
                            AlertLog.queued.is_(True),
                            AlertLog.processed.is_(False),
                        )
                    )
                ).scalar()
                or 0
            )
            if int(already_queued) > 0:
                continue

            candidates.append(
                {
                    "ticker": symbol,
                    "db_qty": float(db_qty or 0.0),
                    "earliest_entry": earliest_entry,
                    "failed_alert_id": failed_sell.id,
                    "failed_at": failed_sell.received_at,
                    "reason": reason,
                }
            )

    if not candidates:
        return []

    kis = await get_kis_client()
    verified: list[dict[str, Any]] = []
    for item in candidates:
        symbol = item["ticker"]
        try:
            if is_kis_domestic_symbol(symbol):
                balance = await kis.get_domestic_symbol_balance(symbol)
            else:
                balance = await kis.get_symbol_balance(symbol)
        except Exception as exc:
            item["kis_error"] = str(exc)
            logger.warning("Missed SELL KIS balance check failed", ticker=symbol, error=str(exc))
            continue

        kis_qty = float(balance.get("qty", 0.0) or 0.0)
        orderable_qty = float(balance.get("orderable_qty", 0.0) or 0.0)
        if kis_qty <= 0:
            continue

        item["kis_qty"] = kis_qty
        item["orderable_qty"] = orderable_qty
        item["avg_price"] = float(balance.get("avg_price", 0.0) or 0.0)
        verified.append(item)

    return verified


async def enqueue_safety_sell(ticker: str, *, reason: str = "missed_sell_repair") -> dict[str, Any]:
    """Create an auditable safety SELL alert and enqueue it."""
    symbol = _normalize_ticker(ticker)
    if not symbol:
        raise ValueError("ticker is required")

    now = datetime.now(timezone.utc)
    alert_id = f"safety-resell-{symbol}-{int(now.timestamp())}"
    raw_payload = {
        "source": "safety_watchdog",
        "action": "SELL",
        "ticker": symbol,
        "reason": reason,
        "created_at": now.isoformat(),
    }
    idempotency_key = hashlib.sha256(
        json.dumps(raw_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    async with get_session() as session:
        alert = AlertLog(
            ticker=symbol,
            action="SELL",
            price=None,
            alert_id=alert_id,
            raw_payload=json.dumps(raw_payload, ensure_ascii=False),
            source_ip="safety_watchdog",
            processed=False,
            queued=False,
            skipped=False,
            skip_reason=None,
            received_at=now,
            idempotency_key=idempotency_key,
        )
        session.add(alert)
        await session.flush()
        alert_log_id = alert.id

    order_data = {
        "action": "SELL",
        "ticker": symbol,
        "price": None,
        "alert_id": alert_id,
        "alert_log_id": alert_log_id,
        "idempotency_key": idempotency_key,
        "retry_count": 0,
        "received_at": now.isoformat(),
        "safety_reason": reason,
    }

    queued_for = "active" if is_market_open_for_ticker(symbol) else "pending"
    if queued_for == "active":
        await enqueue_order(order_data)
    else:
        await enqueue_pending(order_data)

    async with get_session() as session:
        row = (
            await session.execute(select(AlertLog).where(AlertLog.id == alert_log_id))
        ).scalar_one()
        row.queued = True
        row.skipped = False
        row.skip_reason = None

    return {
        "ticker": symbol,
        "alert_log_id": alert_log_id,
        "alert_id": alert_id,
        "queued_for": queued_for,
    }


async def repair_missed_sell_orders(*, notify: bool = True) -> dict[str, Any]:
    """Find missed SELL candidates and enqueue repair SELL orders."""
    from app.notifications.telegram_bot import send_notification

    candidates = await find_missed_sell_candidates()
    enqueued: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for item in candidates:
        symbol = item["ticker"]
        try:
            result = await enqueue_safety_sell(symbol, reason=f"missed_sell_alert:{item['failed_alert_id']}")
            result.update(
                {
                    "kis_qty": item.get("kis_qty"),
                    "orderable_qty": item.get("orderable_qty"),
                    "failed_alert_id": item.get("failed_alert_id"),
                    "failed_at": item.get("failed_at").isoformat() if item.get("failed_at") else None,
                }
            )
            enqueued.append(result)
        except Exception as exc:
            logger.error("Failed to enqueue missed SELL repair", ticker=symbol, error=str(exc))
            errors.append({"ticker": symbol, "error": str(exc)})

    if notify and (enqueued or errors):
        lines = ["🛡️ 매도 누락 자동 점검/복구"]
        if enqueued:
            pending = [item["ticker"] for item in enqueued if item.get("queued_for") == "pending"]
            active = [item["ticker"] for item in enqueued if item.get("queued_for") == "active"]
            if active:
                lines.append(f"즉시 매도 큐 등록: {', '.join(active)}")
            if pending:
                lines.append(f"다음 장 매도 예약: {', '.join(pending)}")
        if errors:
            lines.append("등록 실패: " + ", ".join(f"{e['ticker']}({e['error'][:60]})" for e in errors))
        await send_notification("\n".join(lines))

    return {
        "candidates": candidates,
        "enqueued": enqueued,
        "errors": errors,
    }
