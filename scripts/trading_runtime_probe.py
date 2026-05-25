#!/usr/bin/env python3
"""Collect trading runtime health metrics from inside the app container."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    ROOT = Path(__file__).resolve().parents[1]
except NameError:
    ROOT = Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from app.broker.kis_client import get_kis_client
from app.broker.market_hours import (
    ASIA_MARKET_SESSIONS,
    get_asia_market_status,
    get_krx_market_status,
    get_market_status,
)
from app.cash_monitor import estimate_pending_buy_cash_coverage
from app.config import settings
from app.database.connection import get_session
from app.models.alert_log import AlertLog
from app.models.position import Position, PositionStatus
from app.models.trade import Trade, TradeStatus
from app.notifications import telegram_bot as telegram_bot_module
from app.queue.order_queue import get_queue_stats, get_redis


async def gather_probe() -> dict:
    now = datetime.now(timezone.utc)
    failed_since = now - timedelta(hours=6)
    stale_pending_cutoff = now - timedelta(hours=max(1.0, float(settings.pending_order_ttl_hours or 96.0)))

    result: dict = {
        "ok": True,
        "checked_at_utc": now.isoformat(),
        "market": get_market_status(),
        "markets": {
            "US": get_market_status(),
            "KRX": get_krx_market_status(),
            **{
                market_key: get_asia_market_status(market_key)
                for market_key in ASIA_MARKET_SESSIONS
            },
        },
        "queue": await get_queue_stats(),
        "poller": {},
        "db_open_tickers": 0,
        "db_open_symbols": [],
        "kis_open_tickers": 0,
        "kis_open_symbols": [],
        "kis_domestic_error": None,
        "kis_purchase_usd": None,
        "kis_symbol_check_skipped": False,
        "position_mismatch_symbols": [],
        "failed_trades_last_6h": 0,
        "failed_trade_samples": [],
        "failed_alerts_last_2h": 0,
        "stale_pending_alerts": 0,
        "stale_pending_samples": [],
        "missed_sell_candidates": 0,
        "missed_sell_samples": [],
        "pending_buy_cash_coverage": {},
        "pending_oldest_minutes": None,
        "error": None,
        "kis_error": None,
    }

    try:
        redis_client = await get_redis()
        owner = await redis_client.get(telegram_bot_module._TELEGRAM_POLLER_LOCK_KEY)
        telegram_bot_module._telegram_poller_instance_id = owner
        result["poller"] = await telegram_bot_module._get_telegram_poller_health()
    except Exception as exc:
        result["poller"] = {"ok": False, "status": "확인실패", "error": str(exc), "owner": None, "ttl": None, "is_self": False}

    try:
        async with get_session() as session:
            db_rows = (
                await session.execute(
                    select(Position.ticker).where(Position.status == PositionStatus.OPEN)
                )
            ).scalars().all()
            db_symbols = sorted({str(t or "").strip().upper() for t in db_rows if str(t or "").strip()})
            result["db_open_tickers"] = len(db_symbols)
            result["db_open_symbols"] = db_symbols

            failed_rows = (
                await session.execute(
                    select(Trade.side, Trade.ticker, Trade.error_message, Trade.created_at)
                    .where(Trade.status == TradeStatus.FAILED, Trade.created_at >= failed_since)
                    .order_by(Trade.created_at.desc())
                    .limit(10)
                )
            ).all()
            result["failed_trades_last_6h"] = len(failed_rows)
            result["failed_trade_samples"] = [
                {
                    "side": getattr(side, "value", str(side)),
                    "ticker": ticker,
                    "error": str(error_message or "")[:220],
                    "created_at": created_at.isoformat() if created_at else None,
                }
                for side, ticker, error_message, created_at in failed_rows
            ]

            result["failed_alerts_last_2h"] = (
                (
                    await session.execute(
                        select(func.count(AlertLog.id)).where(
                            AlertLog.skipped.is_(True),
                            AlertLog.received_at >= failed_since,
                        )
                    )
                ).scalar()
                or 0
            )

            stale_rows = (
                await session.execute(
                    select(AlertLog.action, AlertLog.ticker, AlertLog.received_at)
                    .where(
                        AlertLog.queued.is_(True),
                        AlertLog.processed.is_(False),
                        AlertLog.received_at < stale_pending_cutoff,
                    )
                    .order_by(AlertLog.received_at.asc())
                    .limit(10)
                )
            ).all()
            result["stale_pending_alerts"] = len(stale_rows)
            result["stale_pending_samples"] = [
                {
                    "action": action,
                    "ticker": ticker,
                    "received_at": received_at.isoformat() if received_at else None,
                }
                for action, ticker, received_at in stale_rows
            ]

            oldest_pending = (
                (
                    await session.execute(
                        select(func.min(AlertLog.received_at)).where(
                            AlertLog.queued.is_(True),
                            AlertLog.processed.is_(False),
                        )
                    )
                ).scalar()
            )
            if oldest_pending:
                result["pending_oldest_minutes"] = round((now - oldest_pending).total_seconds() / 60.0, 1)

            from app.trading_safety import find_missed_sell_candidates

            missed_sells = await find_missed_sell_candidates()
            result["missed_sell_candidates"] = len(missed_sells)
            result["missed_sell_samples"] = [
                {
                    "ticker": item.get("ticker"),
                    "kis_qty": item.get("kis_qty"),
                    "failed_alert_id": item.get("failed_alert_id"),
                    "failed_at": item.get("failed_at").isoformat() if item.get("failed_at") else None,
                    "reason": str(item.get("reason") or "")[:180],
                }
                for item in missed_sells[:10]
            ]
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"db_probe_failed: {exc}"
        return result

    try:
        result["pending_buy_cash_coverage"] = await estimate_pending_buy_cash_coverage()
    except Exception as exc:
        result["pending_buy_cash_coverage"] = {"ok": False, "error": str(exc)}

    try:
        kis = await get_kis_client()
        kis_rows = list(await kis.get_overseas_balance())
        try:
            kis_rows.extend(list(await kis.get_domestic_balance()))
        except Exception as exc:
            result["kis_domestic_error"] = str(exc)

        def _kis_row_symbol(row: dict) -> str:
            return str(
                row.get("ticker")
                or row.get("ovrs_pdno")
                or row.get("pdno")
                or row.get("pdno_code")
                or ""
            ).strip().upper()

        kis_symbols = sorted(
            {
                _kis_row_symbol(row)
                for row in kis_rows
                if _kis_row_symbol(row)
            }
        )
        result["kis_open_tickers"] = len(kis_symbols)
        result["kis_open_symbols"] = kis_symbols

        try:
            summary = await kis.get_overseas_balance_summary()
            result["kis_purchase_usd"] = float(summary.get("purchase_usd") or 0.0)
        except Exception:
            summary = None

        if kis_symbols:
            result["position_mismatch_symbols"] = sorted(
                set(result["db_open_symbols"]) ^ set(kis_symbols)
            )
        else:
            result["kis_symbol_check_skipped"] = True
            result["position_mismatch_symbols"] = []
    except Exception as exc:
        result["kis_error"] = str(exc)
        result["position_mismatch_symbols"] = []

    return result


async def main() -> int:
    result = await gather_probe()
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
