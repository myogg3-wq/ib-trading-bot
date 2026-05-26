"""
Order execution logic.
BUY: $N market order (configurable via Telegram)
SELL: 100% market sell of all positions for the ticker
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
import structlog
from sqlalchemy import select, func, and_, or_

from app.config import settings
from app.broker.ib_client import get_ib_client
from app.broker.kis_client import get_kis_client
from app.broker.market_hours import get_et_day_bounds_utc, get_kst_day_bounds_utc
from app.gateway.symbol_mapper import (
    to_ib_contract,
    parse_tv_ticker,
    is_kis_domestic_symbol,
    canonical_trade_symbol,
    kis_overseas_currency,
)
from app.database.connection import get_session, get_bot_settings
from app.models.position import Position, PositionStatus
from app.models.trade import Trade, TradeSide, TradeStatus

logger = structlog.get_logger()


def _normalize_broker_name(value: str, fallback: str) -> str:
    name = (value or "").strip().lower()
    if name not in ("ib", "kis"):
        return fallback
    return name


def _broker_execution_chain() -> list[str]:
    mode = (settings.broker_mode or "kis_only").strip().lower()

    if mode == "ib_only":
        return ["ib"]
    if mode == "kis_only":
        return ["kis"]
    if mode == "dual_failover":
        primary = _normalize_broker_name(settings.primary_broker, "ib")
        secondary = _normalize_broker_name(settings.secondary_broker, "kis")
        if primary == secondary:
            return [primary]
        return [primary, secondary]

    logger.warning("Unknown BROKER_MODE, fallback to kis_only", broker_mode=mode)
    return ["kis"]


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _kis_synthetic_order_id(raw_order_id: str, symbol: str, side: str) -> int:
    seed = f"{raw_order_id or ''}|{symbol}|{side}|{datetime.now(timezone.utc).isoformat()}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    numeric = int(digest[:16], 16) % 2_147_483_647
    return -max(1, numeric)


def _is_kis_position(pos: Position) -> bool:
    return bool(pos.entry_order_id is not None and pos.entry_order_id < 0)


def _is_ib_or_legacy_position(pos: Position) -> bool:
    return bool(pos.entry_order_id is None or pos.entry_order_id >= 0)


def _result_currency_for_symbol(symbol: str) -> str:
    if is_kis_domestic_symbol(symbol):
        return "KRW"
    return kis_overseas_currency(symbol)


def _filled_trade_time_window(start_utc, end_utc):
    return or_(
        and_(
            Trade.filled_at.is_not(None),
            Trade.filled_at >= start_utc,
            Trade.filled_at < end_utc,
        ),
        and_(
            Trade.filled_at.is_(None),
            Trade.created_at >= start_utc,
            Trade.created_at < end_utc,
        ),
    )


async def _resolve_kis_buy_amount_usd(bot_settings, kis, symbol: str) -> float:
    """Resolve BUY amount for KIS using KRW target when available."""
    fallback_usd = max(float(bot_settings.buy_amount_usd or 0.0), 1.0)
    target_krw = float(getattr(settings, "kis_target_buy_krw", 0.0) or 0.0)
    if target_krw <= 0:
        return round(fallback_usd, 2)

    try:
        funds = await kis.get_effective_usd_orderable(symbol=symbol, order_price=1.0)
        usd_exrt = float(funds.get("usd_exrt", 0.0) or 0.0)
        if usd_exrt > 0:
            return round(max(target_krw / usd_exrt, 1.0), 2)
    except Exception as e:
        logger.warning(
            "KIS KRW target conversion failed; using fallback USD amount",
            ticker=symbol,
            error=str(e),
        )

    return round(fallback_usd, 2)


async def _resolve_kis_overseas_buy_amount(bot_settings, kis, symbol: str) -> tuple[float, str]:
    """Resolve KIS overseas BUY amount in the symbol's market currency."""
    currency = _result_currency_for_symbol(symbol)
    if currency == "USD":
        return await _resolve_kis_buy_amount_usd(bot_settings, kis, symbol), "USD"

    fallback_usd = max(float(bot_settings.buy_amount_usd or 0.0), 1.0)
    target_krw = float(getattr(settings, "kis_target_buy_krw", 0.0) or 0.0)
    try:
        funds = await kis.get_effective_overseas_orderable(symbol=symbol, order_price=1.0)
        exrt = float(funds.get("exchange_rate_krw", 0.0) or 0.0)
        if target_krw > 0 and exrt > 0:
            return round(max(target_krw / exrt, 1.0), 8), currency
    except Exception as e:
        logger.warning(
            "KIS KRW target conversion failed; using fallback overseas amount",
            ticker=symbol,
            currency=currency,
            error=str(e),
        )

    return round(fallback_usd, 2), currency


async def _reconcile_kis_symbol_to_db(kis, symbol: str, alert_id: str | None = None) -> dict:
    """
    Reconcile one symbol between KIS real holdings and DB OPEN(KIS) rows.
    - Adds missing synthetic BUY rows when KIS qty > DB qty.
    - Closes stale DB rows when DB qty > KIS qty.
    """
    balance = await kis.get_symbol_balance(symbol)
    broker_qty = float(balance.get("qty", 0.0) or 0.0)
    broker_avg = float(balance.get("avg_price", 0.0) or 0.0)
    now = datetime.now(timezone.utc)
    reconcile_order_id = _kis_synthetic_order_id(f"reconcile-kis-{symbol}-{int(now.timestamp())}", symbol, "RECON")

    async with get_session() as session:
        result = await session.execute(
            select(Position).where(
                Position.ticker == symbol,
                Position.status == PositionStatus.OPEN,
                Position.entry_order_id < 0,
            ).order_by(Position.entry_time.asc(), Position.id.asc())
        )
        open_positions = list(result.scalars().all())
        db_qty = sum(float(pos.qty or 0.0) for pos in open_positions)

        closed_qty = 0.0
        if db_qty > broker_qty + 0.0001:
            qty_to_close = round(db_qty - broker_qty, 4)
            for pos in open_positions:
                if qty_to_close <= 0:
                    break
                pos_qty = float(pos.qty or 0.0)
                if pos_qty <= 0:
                    continue
                close_qty = min(pos_qty, qty_to_close)
                close_amount = round((float(pos.entry_amount_usd or 0.0) / pos_qty) * close_qty, 8)

                if close_qty >= pos_qty - 0.0001:
                    pos.exit_price = pos.entry_price
                    pos.exit_amount_usd = pos.entry_amount_usd
                    pos.exit_time = now
                    pos.pnl_usd = 0.0
                    pos.pnl_pct = 0.0
                    pos.status = PositionStatus.CLOSED
                    pos.exit_order_id = reconcile_order_id
                else:
                    remaining_qty = round(pos_qty - close_qty, 4)
                    remaining_amount = round(float(pos.entry_amount_usd or 0.0) - close_amount, 8)
                    closed_position = Position(
                        ticker=pos.ticker,
                        qty=close_qty,
                        entry_price=pos.entry_price,
                        entry_amount_usd=close_amount,
                        entry_time=pos.entry_time,
                        exit_price=pos.entry_price,
                        exit_amount_usd=close_amount,
                        exit_time=now,
                        pnl_usd=0.0,
                        pnl_pct=0.0,
                        status=PositionStatus.CLOSED,
                        entry_order_id=pos.entry_order_id,
                        exit_order_id=reconcile_order_id,
                    )
                    session.add(closed_position)
                    pos.qty = remaining_qty
                    pos.entry_amount_usd = remaining_amount
                    pos.updated_at = now

                qty_to_close = round(qty_to_close - close_qty, 4)
                closed_qty += close_qty

            db_qty = sum(
                float(pos.qty or 0.0)
                for pos in open_positions
                if pos.status == PositionStatus.OPEN
            )

        diff = round(broker_qty - db_qty, 4)
        if diff <= 0:
            return {
                "ok": True,
                "reconciled": closed_qty > 0,
                "added_qty": 0.0,
                "closed_qty": round(closed_qty, 4),
            }

        entry_price = broker_avg
        if entry_price <= 0:
            entry_price = float(await kis.get_quote_price(symbol) or 0.0)
        if entry_price <= 0:
            return {
                "ok": False,
                "error": f"{symbol}: KIS 평균단가/현재가를 찾지 못해 정합화에 실패했습니다.",
            }

        fill_amount = round(diff * entry_price, 2)
        reconcile_alert_id = alert_id or f"reconcile-kis-{symbol}-{int(now.timestamp())}"
        synthetic_order_id = _kis_synthetic_order_id(reconcile_alert_id, symbol, "BUY")

        session.add(
            Position(
                ticker=symbol,
                qty=diff,
                entry_price=entry_price,
                entry_amount_usd=fill_amount,
                entry_time=now,
                status=PositionStatus.OPEN,
                entry_order_id=synthetic_order_id,
            )
        )
        session.add(
            Trade(
                ticker=symbol,
                side=TradeSide.BUY,
                order_type="MKT",
                requested_qty=diff,
                filled_qty=diff,
                requested_amount_usd=fill_amount,
                avg_fill_price=entry_price,
                total_fill_amount_usd=fill_amount,
                commission=0.0,
                ib_order_id=synthetic_order_id,
                status=TradeStatus.FILLED,
                alert_id=reconcile_alert_id,
                created_at=now,
                filled_at=now,
            )
        )

    logger.warning(
        "KIS/DB qty mismatch reconciled",
        ticker=symbol,
        broker_qty=broker_qty,
        db_qty=db_qty,
        added_qty=diff,
        closed_qty=round(closed_qty, 4),
    )
    return {
        "ok": True,
        "reconciled": True,
        "added_qty": diff,
        "closed_qty": round(closed_qty, 4),
        "price": round(entry_price, 8),
        "amount": round(fill_amount, 2),
        "alert_id": reconcile_alert_id,
    }


async def _reconcile_kis_domestic_symbol_to_db(kis, symbol: str, alert_id: str | None = None) -> dict:
    """
    Reconcile one domestic/KRX symbol between KIS real holdings and DB OPEN(KIS) rows.
    Amounts are stored in the existing amount columns in native KRW for numeric KRX symbols.
    """
    balance = await kis.get_domestic_symbol_balance(symbol)
    broker_qty = float(balance.get("qty", 0.0) or 0.0)
    broker_avg = float(balance.get("avg_price", 0.0) or 0.0)
    now = datetime.now(timezone.utc)
    reconcile_order_id = _kis_synthetic_order_id(f"reconcile-kis-krx-{symbol}-{int(now.timestamp())}", symbol, "RECON")

    async with get_session() as session:
        result = await session.execute(
            select(Position).where(
                Position.ticker == symbol,
                Position.status == PositionStatus.OPEN,
                Position.entry_order_id < 0,
            ).order_by(Position.entry_time.asc(), Position.id.asc())
        )
        open_positions = list(result.scalars().all())
        db_qty = sum(float(pos.qty or 0.0) for pos in open_positions)

        closed_qty = 0.0
        if db_qty > broker_qty + 0.0001:
            qty_to_close = round(db_qty - broker_qty, 4)
            for pos in open_positions:
                if qty_to_close <= 0:
                    break
                pos_qty = float(pos.qty or 0.0)
                if pos_qty <= 0:
                    continue
                close_qty = min(pos_qty, qty_to_close)
                close_amount = round((float(pos.entry_amount_usd or 0.0) / pos_qty) * close_qty, 2)
                if close_qty >= pos_qty - 0.0001:
                    pos.exit_price = pos.entry_price
                    pos.exit_amount_usd = pos.entry_amount_usd
                    pos.exit_time = now
                    pos.pnl_usd = 0.0
                    pos.pnl_pct = 0.0
                    pos.status = PositionStatus.CLOSED
                    pos.exit_order_id = reconcile_order_id
                else:
                    remaining_qty = round(pos_qty - close_qty, 4)
                    remaining_amount = round(float(pos.entry_amount_usd or 0.0) - close_amount, 2)
                    closed_position = Position(
                        ticker=pos.ticker,
                        qty=close_qty,
                        entry_price=pos.entry_price,
                        entry_amount_usd=close_amount,
                        entry_time=pos.entry_time,
                        exit_price=pos.entry_price,
                        exit_amount_usd=close_amount,
                        exit_time=now,
                        pnl_usd=0.0,
                        pnl_pct=0.0,
                        status=PositionStatus.CLOSED,
                        entry_order_id=pos.entry_order_id,
                        exit_order_id=reconcile_order_id,
                    )
                    session.add(closed_position)
                    pos.qty = remaining_qty
                    pos.entry_amount_usd = remaining_amount
                    pos.updated_at = now

                qty_to_close = round(qty_to_close - close_qty, 4)
                closed_qty += close_qty

            db_qty = sum(
                float(pos.qty or 0.0)
                for pos in open_positions
                if pos.status == PositionStatus.OPEN
            )

        diff = round(broker_qty - db_qty, 4)
        if diff <= 0:
            return {
                "ok": True,
                "reconciled": closed_qty > 0,
                "added_qty": 0.0,
                "closed_qty": round(closed_qty, 4),
            }

        entry_price = broker_avg
        if entry_price <= 0:
            entry_price = float(await kis.get_domestic_quote_price(symbol) or 0.0)
        if entry_price <= 0:
            return {
                "ok": False,
                "error": f"{symbol}: KIS 국내 평균단가/현재가를 찾지 못해 정합화에 실패했습니다.",
            }

        fill_amount = round(diff * entry_price, 2)
        reconcile_alert_id = alert_id or f"reconcile-kis-krx-{symbol}-{int(now.timestamp())}"
        synthetic_order_id = _kis_synthetic_order_id(reconcile_alert_id, symbol, "BUY")

        session.add(
            Position(
                ticker=symbol,
                qty=diff,
                entry_price=entry_price,
                entry_amount_usd=fill_amount,
                entry_time=now,
                status=PositionStatus.OPEN,
                entry_order_id=synthetic_order_id,
            )
        )
        session.add(
            Trade(
                ticker=symbol,
                side=TradeSide.BUY,
                order_type="MKT",
                requested_qty=diff,
                filled_qty=diff,
                requested_amount_usd=fill_amount,
                avg_fill_price=entry_price,
                total_fill_amount_usd=fill_amount,
                commission=0.0,
                ib_order_id=synthetic_order_id,
                status=TradeStatus.FILLED,
                alert_id=reconcile_alert_id,
                created_at=now,
                filled_at=now,
            )
        )

    logger.warning(
        "KIS domestic/DB qty mismatch reconciled",
        ticker=symbol,
        broker_qty=broker_qty,
        db_qty=db_qty,
        added_qty=diff,
        closed_qty=round(closed_qty, 4),
    )
    return {
        "ok": True,
        "reconciled": True,
        "added_qty": diff,
        "closed_qty": round(closed_qty, 4),
        "price": round(entry_price, 8),
        "amount": round(fill_amount, 2),
        "alert_id": reconcile_alert_id,
    }


async def _confirm_kis_buy_after_uncertain_failure(
    kis,
    symbol: str,
    alert_id: str,
    *,
    domestic: bool = False,
    attempts: int = 6,
    delay_seconds: float = 3.0,
) -> dict:
    """
    KIS can occasionally report an unfilled/cancel problem while the order later
    appears in the real balance. Poll the broker balance before declaring failure.
    """
    last_error = ""
    for attempt in range(max(1, attempts)):
        if attempt > 0:
            await asyncio.sleep(delay_seconds)
        try:
            if domestic:
                sync_result = await _reconcile_kis_domestic_symbol_to_db(kis, symbol, alert_id=alert_id)
            else:
                sync_result = await _reconcile_kis_symbol_to_db(kis, symbol, alert_id=alert_id)
        except Exception as exc:
            last_error = str(exc)
            continue

        if not sync_result.get("ok", False):
            last_error = sync_result.get("error", "")
            continue

        added_qty = float(sync_result.get("added_qty", 0.0) or 0.0)
        if added_qty > 0:
            price = float(sync_result.get("price", 0.0) or 0.0)
            amount = float(sync_result.get("amount", 0.0) or 0.0)
            logger.warning(
                "KIS BUY recovered after uncertain failure",
                ticker=symbol,
                qty=added_qty,
                price=price,
                amount=amount,
                domestic=domestic,
            )
            return {
                "success": True,
                "action": "BUY",
                "broker": "KIS",
                "ticker": symbol,
                "qty": added_qty,
                "price": price,
                "amount": round(amount, 2),
                "commission": 0.0,
                "order_id": sync_result.get("alert_id") or alert_id,
                "currency": "KRW" if domestic else _result_currency_for_symbol(symbol),
                "recovered_after_uncertain_failure": True,
            }

    return {
        "success": False,
        "error": last_error or f"{symbol}: KIS 잔고 재확인 후에도 체결을 확인하지 못했습니다",
    }


async def _count_today_filled_buys(symbol: str) -> int:
    """Count today's FILLED BUY rows for a symbol in the relevant market day."""
    if is_kis_domestic_symbol(symbol) or _result_currency_for_symbol(symbol) in ("KRW", "HKD", "CNY", "JPY"):
        today_start, today_end = get_kst_day_bounds_utc()
    else:
        today_start, today_end = get_et_day_bounds_utc()
    async with get_session() as session:
        result = await session.execute(
            select(func.count(Trade.id)).where(
                Trade.ticker == symbol,
                Trade.side == TradeSide.BUY,
                Trade.status == TradeStatus.FILLED,
                _filled_trade_time_window(today_start, today_end),
            )
        )
        return int(result.scalar() or 0)


async def execute_buy(ticker: str, alert_id: str = "") -> dict:
    """
    Execute BUY with broker routing.
    - ib_only: IBKR only
    - kis_only: KIS only
    - dual_failover: primary broker first, then secondary on failure
    """
    chain = _broker_execution_chain()
    failures = []

    for broker in chain:
        if broker == "ib":
            result = await _execute_buy_ib(ticker, alert_id)
        else:
            result = await _execute_buy_kis(ticker, alert_id)

        if result.get("success"):
            if failures:
                result["failover_errors"] = failures
            return result
        if result.get("skipped"):
            return result

        failures.append(f"{broker.upper()}: {result.get('error', 'unknown')}")

    return {
        "success": False,
        "error": "모든 브로커 매수 실패: " + " | ".join(failures),
    }


async def execute_sell(ticker: str, alert_id: str = "") -> dict:
    """
    Execute SELL with broker routing.
    In dual mode, fallback is allowed, but each broker function guards against
    cross-broker position liquidation to prevent accidental wrong-account sells.
    """
    chain = _broker_execution_chain()
    failures = []

    for broker in chain:
        if broker == "ib":
            result = await _execute_sell_ib(ticker, alert_id)
        else:
            result = await _execute_sell_kis(ticker, alert_id)

        if result.get("success"):
            if failures:
                result["failover_errors"] = failures
            return result
        if result.get("skipped"):
            return result

        failures.append(f"{broker.upper()}: {result.get('error', 'unknown')}")

    return {
        "success": False,
        "error": "모든 브로커 매도 실패: " + " | ".join(failures),
    }


async def _execute_buy_ib(ticker: str, alert_id: str = "") -> dict:
    """
    Execute BUY via IBKR.

    Steps:
    1. Get current buy amount from settings
    2. Get snapshot price from IB
    3. Calculate quantity ($amount / price)
    4. Place market order
    5. Record position and trade in DB
    """
    bot_settings = await get_bot_settings()
    buy_amount = bot_settings.buy_amount_usd

    ib = await get_ib_client()
    contract = to_ib_contract(ticker)

    # Qualify the contract (resolve to specific exchange)
    try:
        qualified = await ib.ib.qualifyContractsAsync(contract)
        if not qualified:
            return {"success": False, "error": f"{ticker} 종목 계약 조회에 실패했습니다"}
        contract = qualified[0]
    except Exception as e:
        return {"success": False, "error": f"종목 계약 조회 실패: {str(e)}"}

    # Get current price
    price = await ib.get_snapshot_price(contract)
    if not price or price <= 0:
        return {"success": False, "error": f"{ticker} 현재가를 가져올 수 없습니다"}

    # Calculate quantity
    quantity = round(buy_amount / price, 4)
    if quantity <= 0:
        return {"success": False, "error": f"{ticker} 수량 계산 결과가 0입니다 (현재가 ${price})"}

    # Place market order via IB
    try:
        order_result = await ib.place_market_order(contract, "BUY", quantity)
    except Exception as e:
        return {"success": False, "error": f"매수 주문 전송 실패: {str(e)}"}

    if not order_result["filled"]:
        # Record failed trade
        async with get_session() as session:
            trade = Trade(
                ticker=parse_tv_ticker(ticker)["symbol"],
                side=TradeSide.BUY,
                order_type="MKT",
                requested_qty=quantity,
                requested_amount_usd=buy_amount,
                ib_order_id=order_result.get("order_id"),
                status=TradeStatus.FAILED,
                error_message=f"주문 상태: {order_result['status']}",
                alert_id=alert_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)

        return {
            "success": False,
            "error": f"주문이 체결되지 않았습니다. 상태: {order_result['status']}",
            "order_id": order_result.get("order_id"),
            "broker": "IBKR",
        }

    # Record successful trade and position
    symbol = parse_tv_ticker(ticker)["symbol"]
    fill_price = order_result["avg_fill_price"]
    fill_qty = order_result["filled_qty"]
    fill_amount = fill_price * fill_qty

    async with get_session() as session:
        # Create position record
        position = Position(
            ticker=symbol,
            qty=fill_qty,
            entry_price=fill_price,
            entry_amount_usd=fill_amount,
            entry_time=datetime.now(timezone.utc),
            status=PositionStatus.OPEN,
            entry_order_id=order_result["order_id"],
        )
        session.add(position)

        # Create trade record
        trade = Trade(
            ticker=symbol,
            side=TradeSide.BUY,
            order_type="MKT",
            requested_qty=quantity,
            filled_qty=fill_qty,
            requested_amount_usd=buy_amount,
            avg_fill_price=fill_price,
            total_fill_amount_usd=fill_amount,
            commission=order_result.get("commission", 0),
            ib_order_id=order_result["order_id"],
            ib_perm_id=order_result.get("perm_id"),
            status=TradeStatus.FILLED,
            alert_id=alert_id,
            created_at=datetime.now(timezone.utc),
            filled_at=datetime.now(timezone.utc),
        )
        session.add(trade)

    logger.info(
        "BUY executed",
        ticker=symbol,
        qty=fill_qty,
        price=fill_price,
        amount=round(fill_amount, 2),
    )

    return {
        "success": True,
        "action": "BUY",
        "broker": "IBKR",
        "ticker": symbol,
        "qty": fill_qty,
        "price": fill_price,
        "amount": round(fill_amount, 2),
        "commission": order_result.get("commission", 0),
        "order_id": order_result["order_id"],
    }


async def _execute_buy_kis(ticker: str, alert_id: str = "") -> dict:
    """Execute BUY via KIS Open API."""
    bot_settings = await get_bot_settings()
    symbol = canonical_trade_symbol(ticker)

    if is_kis_domestic_symbol(symbol):
        return await _execute_buy_kis_domestic(symbol, alert_id)

    kis = await get_kis_client()
    if not kis.is_configured:
        return {"success": False, "error": "KIS 설정 누락 (.env의 KIS_* 값 필요)"}

    try:
        sync_result = await _reconcile_kis_symbol_to_db(kis, symbol)
    except Exception as e:
        return {"success": False, "error": f"KIS/DB 수량 정합화 실패: {str(e)}"}
    if not sync_result.get("ok", False):
        return {"success": False, "error": sync_result.get("error", "KIS/DB 정합화 실패")}

    today_filled = await _count_today_filled_buys(symbol)
    if today_filled >= 1:
        return {
            "success": False,
            "error": f"{symbol}: 오늘 매수는 1회만 허용됩니다 ({today_filled}/1)",
        }

    buy_amount, currency = await _resolve_kis_overseas_buy_amount(bot_settings, kis, symbol)

    try:
        order_result = await kis.place_buy_by_amount(symbol, buy_amount)
    except Exception as e:
        error_text = f"KIS 매수 요청 실패: {str(e)}"
        recovered = await _confirm_kis_buy_after_uncertain_failure(
            kis,
            symbol,
            alert_id,
            domestic=False,
        )
        if recovered.get("success"):
            recovered["warning"] = error_text
            return recovered

        async with get_session() as session:
            trade = Trade(
                ticker=symbol,
                side=TradeSide.BUY,
                order_type="MKT",
                requested_amount_usd=buy_amount,
                status=TradeStatus.FAILED,
                error_message=f"KIS: {error_text}",
                alert_id=alert_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)
        return {"success": False, "error": error_text}

    if not order_result.get("success"):
        error_text = order_result.get("error", "KIS 주문 실패")
        recovered = await _confirm_kis_buy_after_uncertain_failure(
            kis,
            symbol,
            alert_id,
            domestic=False,
        )
        if recovered.get("success"):
            recovered["warning"] = error_text
            return recovered

        async with get_session() as session:
            trade = Trade(
                ticker=symbol,
                side=TradeSide.BUY,
                order_type="MKT",
                requested_amount_usd=buy_amount,
                status=TradeStatus.FAILED,
                error_message=f"KIS: {error_text}",
                alert_id=alert_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)
        return {"success": False, "error": error_text}

    fill_price = float(order_result["price"])
    fill_qty = float(order_result["qty"])
    fill_amount = float(order_result["amount"])
    raw_order_id = str(order_result.get("order_id", "")).strip()
    synthetic_order_id = _kis_synthetic_order_id(raw_order_id, symbol, "BUY")

    try:
        async with get_session() as session:
            position = Position(
                ticker=symbol,
                qty=fill_qty,
                entry_price=fill_price,
                entry_amount_usd=fill_amount,
                entry_time=datetime.now(timezone.utc),
                status=PositionStatus.OPEN,
                # KIS 주문은 음수 synthetic ID로 저장 (브로커 식별용).
                entry_order_id=synthetic_order_id,
            )
            session.add(position)

            trade = Trade(
                ticker=symbol,
                side=TradeSide.BUY,
                order_type="MKT",
                requested_qty=fill_qty,
                filled_qty=fill_qty,
                requested_amount_usd=buy_amount,
                avg_fill_price=fill_price,
                total_fill_amount_usd=fill_amount,
                commission=order_result.get("commission", 0.0),
                ib_order_id=synthetic_order_id,
                status=TradeStatus.FILLED,
                alert_id=alert_id,
                created_at=datetime.now(timezone.utc),
                filled_at=datetime.now(timezone.utc),
            )
            session.add(trade)
    except Exception as db_err:
        # Broker fill already happened. Do not mark as failed to avoid duplicate retries.
        logger.error(
            "KIS BUY persisted failed after broker fill",
            ticker=symbol,
            qty=fill_qty,
            price=fill_price,
            error=str(db_err),
        )
        return {
            "success": True,
            "action": "BUY",
            "broker": "KIS",
            "ticker": symbol,
            "qty": fill_qty,
            "price": fill_price,
            "amount": round(fill_amount, 2),
            "commission": order_result.get("commission", 0.0),
            "order_id": raw_order_id or synthetic_order_id,
            "currency": currency,
        }

    logger.info(
        "BUY executed via KIS",
        ticker=symbol,
        qty=fill_qty,
        price=fill_price,
        amount=round(fill_amount, 2),
    )

    return {
        "success": True,
        "action": "BUY",
        "broker": "KIS",
        "ticker": symbol,
        "qty": fill_qty,
        "price": fill_price,
        "amount": round(fill_amount, 2),
        "commission": order_result.get("commission", 0.0),
        "order_id": raw_order_id or synthetic_order_id,
        "currency": currency,
    }


async def _execute_buy_kis_domestic(symbol: str, alert_id: str = "") -> dict:
    """Execute BUY via KIS domestic/KRX Open API."""
    if not settings.kis_domestic_enabled:
        return {"success": False, "error": "KIS 국내주식 자동매매가 비활성화되어 있습니다"}

    kis = await get_kis_client()
    if not kis.is_configured:
        return {"success": False, "error": "KIS 설정 누락 (.env의 KIS_* 값 필요)"}

    try:
        sync_result = await _reconcile_kis_domestic_symbol_to_db(kis, symbol)
    except Exception as e:
        return {"success": False, "error": f"KIS 국내/DB 수량 정합화 실패: {str(e)}"}
    if not sync_result.get("ok", False):
        return {"success": False, "error": sync_result.get("error", "KIS 국내/DB 정합화 실패")}

    today_filled = await _count_today_filled_buys(symbol)
    if today_filled >= 1:
        return {
            "success": False,
            "error": f"{symbol}: 오늘 매수는 1회만 허용됩니다 ({today_filled}/1)",
        }

    buy_amount_krw = float(settings.kis_domestic_target_buy_krw or settings.kis_target_buy_krw or 100000.0)

    try:
        order_result = await kis.place_domestic_buy_by_amount(symbol, buy_amount_krw)
    except Exception as e:
        error_text = f"KIS 국내 매수 요청 실패: {str(e)}"
        recovered = await _confirm_kis_buy_after_uncertain_failure(
            kis,
            symbol,
            alert_id,
            domestic=True,
        )
        if recovered.get("success"):
            recovered["warning"] = error_text
            return recovered

        async with get_session() as session:
            trade = Trade(
                ticker=symbol,
                side=TradeSide.BUY,
                order_type="MKT",
                requested_amount_usd=buy_amount_krw,
                status=TradeStatus.FAILED,
                error_message=f"KIS-KRX: {error_text}",
                alert_id=alert_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)
        return {"success": False, "error": error_text}

    if not order_result.get("success"):
        error_text = order_result.get("error", "KIS 국내 주문 실패")
        recovered = await _confirm_kis_buy_after_uncertain_failure(
            kis,
            symbol,
            alert_id,
            domestic=True,
        )
        if recovered.get("success"):
            recovered["warning"] = error_text
            return recovered

        async with get_session() as session:
            trade = Trade(
                ticker=symbol,
                side=TradeSide.BUY,
                order_type="MKT",
                requested_amount_usd=buy_amount_krw,
                status=TradeStatus.FAILED,
                error_message=f"KIS-KRX: {error_text}",
                alert_id=alert_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)
        return {"success": False, "error": error_text}

    fill_price = float(order_result["price"])
    fill_qty = float(order_result["qty"])
    fill_amount = float(order_result["amount"])
    raw_order_id = str(order_result.get("order_id", "")).strip()
    synthetic_order_id = _kis_synthetic_order_id(raw_order_id, symbol, "BUY")

    try:
        async with get_session() as session:
            position = Position(
                ticker=symbol,
                qty=fill_qty,
                entry_price=fill_price,
                entry_amount_usd=fill_amount,
                entry_time=datetime.now(timezone.utc),
                status=PositionStatus.OPEN,
                entry_order_id=synthetic_order_id,
            )
            session.add(position)

            trade = Trade(
                ticker=symbol,
                side=TradeSide.BUY,
                order_type="MKT",
                requested_qty=fill_qty,
                filled_qty=fill_qty,
                requested_amount_usd=buy_amount_krw,
                avg_fill_price=fill_price,
                total_fill_amount_usd=fill_amount,
                commission=order_result.get("commission", 0.0),
                ib_order_id=synthetic_order_id,
                status=TradeStatus.FILLED,
                alert_id=alert_id,
                created_at=datetime.now(timezone.utc),
                filled_at=datetime.now(timezone.utc),
            )
            session.add(trade)
    except Exception as db_err:
        # Broker fill already happened. Do not report failure or invite a manual
        # duplicate order; the KIS reconcile job will repair the DB ledger.
        logger.error(
            "KIS domestic BUY persist failed after broker fill",
            ticker=symbol,
            qty=fill_qty,
            price=fill_price,
            error=str(db_err),
        )
        return {
            "success": True,
            "action": "BUY",
            "broker": "KIS",
            "ticker": symbol,
            "qty": fill_qty,
            "price": fill_price,
            "amount": round(fill_amount, 2),
            "commission": order_result.get("commission", 0.0),
            "order_id": raw_order_id or synthetic_order_id,
            "currency": "KRW",
            "db_persist_pending_reconcile": True,
        }

    logger.info(
        "BUY executed via KIS domestic",
        ticker=symbol,
        qty=fill_qty,
        price=fill_price,
        amount=round(fill_amount, 2),
    )

    return {
        "success": True,
        "action": "BUY",
        "broker": "KIS",
        "ticker": symbol,
        "qty": fill_qty,
        "price": fill_price,
        "amount": round(fill_amount, 2),
        "commission": order_result.get("commission", 0.0),
        "order_id": raw_order_id or synthetic_order_id,
        "currency": "KRW",
    }


async def _execute_sell_ib(ticker: str, alert_id: str = "") -> dict:
    """
    Execute SELL via IBKR.

    Steps:
    1. Look up all OPEN positions for this ticker in DB
    2. Sum total quantity
    3. Place single market sell order for total quantity
    4. Close all positions and record P&L
    """
    symbol = parse_tv_ticker(ticker)["symbol"]

    # Get all open positions for this ticker
    async with get_session() as session:
        result = await session.execute(
            select(Position).where(
                Position.ticker == symbol,
                Position.status == PositionStatus.OPEN,
            )
        )
        open_positions = result.scalars().all()

    if not open_positions:
        logger.warning("SELL signal but no open positions", ticker=symbol)
        return {
            "success": False,
            "error": f"{symbol} 보유 포지션이 없습니다",
            "ticker": symbol,
        }

    if any(_is_kis_position(pos) for pos in open_positions):
        return {
            "success": False,
            "error": f"{symbol} 포지션은 KIS 계좌에 있어 IB로 매도할 수 없습니다",
        }

    # Calculate total quantity to sell
    total_qty = sum(pos.qty for pos in open_positions)
    total_entry_amount = sum(pos.entry_amount_usd for pos in open_positions)
    position_count = len(open_positions)

    if total_qty <= 0:
        return {"success": False, "error": f"{symbol} 전체 매도 수량이 0입니다"}

    # Connect to IB and place sell order
    ib = await get_ib_client()
    contract = to_ib_contract(ticker)

    try:
        qualified = await ib.ib.qualifyContractsAsync(contract)
        if qualified:
            contract = qualified[0]
    except Exception as e:
        return {"success": False, "error": f"종목 계약 조회 실패: {str(e)}"}

    try:
        order_result = await ib.place_market_order(contract, "SELL", total_qty)
    except Exception as e:
        return {"success": False, "error": f"매도 주문 전송 실패: {str(e)}"}

    if not order_result["filled"]:
        async with get_session() as session:
            trade = Trade(
                ticker=symbol,
                side=TradeSide.SELL,
                order_type="MKT",
                requested_qty=total_qty,
                ib_order_id=order_result.get("order_id"),
                status=TradeStatus.FAILED,
                error_message=f"주문 상태: {order_result['status']}",
                alert_id=alert_id,
                position_ids=",".join(str(p.id) for p in open_positions),
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)

        return {
            "success": False,
            "error": f"매도 주문이 체결되지 않았습니다. 상태: {order_result['status']}",
            "broker": "IBKR",
        }

    # Calculate P&L
    fill_price = order_result["avg_fill_price"]
    fill_qty = order_result["filled_qty"]
    exit_amount = fill_price * fill_qty
    total_pnl = exit_amount - total_entry_amount
    total_pnl_pct = (total_pnl / total_entry_amount * 100) if total_entry_amount > 0 else 0

    # Close all positions in DB
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        # Re-fetch positions within this session
        result = await session.execute(
            select(Position).where(
                Position.ticker == symbol,
                Position.status == PositionStatus.OPEN,
            )
        )
        positions_to_close = [p for p in result.scalars().all() if _is_ib_or_legacy_position(p)]

        for pos in positions_to_close:
            pos.exit_price = fill_price
            pos.exit_amount_usd = pos.qty * fill_price
            pos.exit_time = now
            pos.pnl_usd = pos.exit_amount_usd - pos.entry_amount_usd
            pos.pnl_pct = (pos.pnl_usd / pos.entry_amount_usd * 100) if pos.entry_amount_usd > 0 else 0
            pos.status = PositionStatus.CLOSED
            pos.exit_order_id = order_result["order_id"]

        # Record trade
        trade = Trade(
            ticker=symbol,
            side=TradeSide.SELL,
            order_type="MKT",
            requested_qty=total_qty,
            filled_qty=fill_qty,
            avg_fill_price=fill_price,
            total_fill_amount_usd=exit_amount,
            commission=order_result.get("commission", 0),
            ib_order_id=order_result["order_id"],
            ib_perm_id=order_result.get("perm_id"),
            status=TradeStatus.FILLED,
            alert_id=alert_id,
            position_ids=",".join(str(p.id) for p in positions_to_close),
            total_pnl_usd=total_pnl,
            created_at=datetime.now(timezone.utc),
            filled_at=now,
        )
        session.add(trade)

    logger.info(
        "SELL executed",
        ticker=symbol,
        positions_closed=position_count,
        qty=fill_qty,
        price=fill_price,
        exit_amount=round(exit_amount, 2),
        pnl=round(total_pnl, 2),
        pnl_pct=round(total_pnl_pct, 2),
    )

    return {
        "success": True,
        "action": "SELL",
        "broker": "IBKR",
        "ticker": symbol,
        "positions_closed": position_count,
        "qty": fill_qty,
        "price": fill_price,
        "entry_total": round(total_entry_amount, 2),
        "exit_total": round(exit_amount, 2),
        "pnl": round(total_pnl, 2),
        "pnl_pct": round(total_pnl_pct, 2),
        "commission": order_result.get("commission", 0),
        "order_id": order_result["order_id"],
    }


async def _apply_kis_sell_fill(
    *,
    symbol: str,
    requested_qty: float,
    filled_qty: float,
    fill_price: float,
    commission: float,
    raw_order_id: str,
    alert_id: str,
    currency: str = "USD",
) -> dict:
    """Apply confirmed KIS SELL fill to DB positions, including partial fills."""
    confirmed_qty = max(float(filled_qty or 0.0), 0.0)
    if confirmed_qty <= 0:
        return {"success": False, "error": f"{symbol} 매도 체결 수량을 확인하지 못했습니다"}

    now = datetime.now(timezone.utc)
    synthetic_order_id = _kis_synthetic_order_id(raw_order_id, symbol, "SELL")

    def _pending_reconcile_result(reason: str) -> dict:
        executed_qty = round(confirmed_qty, 4)
        requested = float(requested_qty or 0.0)
        remaining_qty = max(0.0, round(requested - executed_qty, 4))
        exit_amount = round(executed_qty * float(fill_price or 0.0), 2)
        partial_fill = remaining_qty > 0.0001
        result = {
            "success": True,
            "partial_fill": partial_fill,
            "action": "SELL",
            "broker": "KIS",
            "ticker": symbol,
            "positions_closed": 0,
            "qty": executed_qty,
            "remaining_qty": remaining_qty,
            "price": round(float(fill_price or 0.0), 6),
            "entry_total": 0.0,
            "exit_total": exit_amount,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "commission": commission,
            "order_id": raw_order_id or synthetic_order_id,
            "currency": currency,
            "db_persist_pending_reconcile": True,
            "db_persist_error": reason[:180],
        }
        if not partial_fill:
            result.pop("partial_fill", None)
        return result

    try:
        async with get_session() as session:
            result = await session.execute(
                select(Position).where(
                    Position.ticker == symbol,
                    Position.status == PositionStatus.OPEN,
                ).order_by(Position.entry_time.asc(), Position.id.asc())
            )
            open_positions = [p for p in result.scalars().all() if _is_kis_position(p)]

            qty_to_close = confirmed_qty
            position_ids: list[str] = []
            touched_positions = 0
            total_entry_amount = 0.0
            exit_amount = 0.0
            total_pnl = 0.0

            for pos in open_positions:
                if qty_to_close <= 0.0001:
                    break

                pos_qty = float(pos.qty or 0.0)
                if pos_qty <= 0:
                    continue

                close_qty = min(pos_qty, qty_to_close)
                if close_qty <= 0:
                    continue

                entry_amount = float(pos.entry_amount_usd or 0.0)
                close_entry_amount = round(entry_amount * (close_qty / pos_qty), 8)
                close_exit_amount = round(close_qty * fill_price, 8)
                close_pnl = close_exit_amount - close_entry_amount
                close_pnl_pct = (close_pnl / close_entry_amount * 100) if close_entry_amount > 0 else 0.0

                if close_qty >= pos_qty - 0.0001:
                    pos.exit_price = fill_price
                    pos.exit_amount_usd = close_exit_amount
                    pos.exit_time = now
                    pos.pnl_usd = close_pnl
                    pos.pnl_pct = close_pnl_pct
                    pos.status = PositionStatus.CLOSED
                    pos.exit_order_id = synthetic_order_id
                else:
                    closed_position = Position(
                        ticker=pos.ticker,
                        qty=close_qty,
                        entry_price=pos.entry_price,
                        entry_amount_usd=close_entry_amount,
                        entry_time=pos.entry_time,
                        exit_price=fill_price,
                        exit_amount_usd=close_exit_amount,
                        exit_time=now,
                        pnl_usd=close_pnl,
                        pnl_pct=close_pnl_pct,
                        status=PositionStatus.CLOSED,
                        entry_order_id=pos.entry_order_id,
                        exit_order_id=synthetic_order_id,
                    )
                    session.add(closed_position)
                    pos.qty = round(pos_qty - close_qty, 4)
                    pos.entry_amount_usd = round(entry_amount - close_entry_amount, 8)
                    pos.updated_at = now

                qty_to_close = round(qty_to_close - close_qty, 4)
                total_entry_amount += close_entry_amount
                exit_amount += close_exit_amount
                total_pnl += close_pnl
                position_ids.append(str(pos.id))
                touched_positions += 1

            executed_qty = round(confirmed_qty - max(qty_to_close, 0.0), 4)
            if executed_qty <= 0:
                logger.error(
                    "KIS SELL fill confirmed but no DB position was updated",
                    ticker=symbol,
                    filled_qty=confirmed_qty,
                )
                return _pending_reconcile_result("confirmed_fill_without_matching_db_position")

            trade_status = (
                TradeStatus.FILLED
                if executed_qty >= float(requested_qty or 0.0) - 0.0001
                else TradeStatus.PARTIAL
            )
            remaining_qty = max(0.0, round(float(requested_qty or 0.0) - executed_qty, 4))
            total_pnl_pct = (total_pnl / total_entry_amount * 100) if total_entry_amount > 0 else 0.0

            trade = Trade(
                ticker=symbol,
                side=TradeSide.SELL,
                order_type="MKT",
                requested_qty=float(requested_qty or 0.0),
                filled_qty=executed_qty,
                avg_fill_price=fill_price,
                total_fill_amount_usd=round(exit_amount, 2),
                commission=commission,
                ib_order_id=synthetic_order_id,
                status=trade_status,
                alert_id=alert_id,
                position_ids=",".join(position_ids),
                total_pnl_usd=round(total_pnl, 2),
                error_message=(
                    f"부분체결 {executed_qty:g}/{float(requested_qty or 0.0):g}주"
                    if trade_status == TradeStatus.PARTIAL
                    else None
                ),
                created_at=now,
                filled_at=now,
            )
            session.add(trade)
    except Exception as db_err:
        logger.error(
            "KIS SELL persist failed after broker fill",
            ticker=symbol,
            filled_qty=confirmed_qty,
            price=fill_price,
            error=str(db_err),
        )
        return _pending_reconcile_result(str(db_err))

    logger.info(
        "SELL applied via KIS",
        ticker=symbol,
        requested_qty=requested_qty,
        filled_qty=executed_qty,
        remaining_qty=remaining_qty,
        price=fill_price,
        exit_amount=round(exit_amount, 2),
        pnl=round(total_pnl, 2),
        trade_status=trade_status.value,
    )

    return {
        "success": True,
        "partial_fill": trade_status == TradeStatus.PARTIAL,
        "action": "SELL",
        "broker": "KIS",
        "ticker": symbol,
        "positions_closed": touched_positions,
        "qty": executed_qty,
        "remaining_qty": remaining_qty,
        "price": round(fill_price, 6),
        "entry_total": round(total_entry_amount, 2),
        "exit_total": round(exit_amount, 2),
        "pnl": round(total_pnl, 2),
        "pnl_pct": round(total_pnl_pct, 2),
        "commission": commission,
        "order_id": raw_order_id or synthetic_order_id,
        "currency": currency,
    }


async def _execute_sell_kis_domestic(symbol: str, alert_id: str = "") -> dict:
    """Execute SELL via KIS domestic/KRX Open API."""
    if not settings.kis_domestic_enabled:
        return {"success": False, "error": "KIS 국내주식 자동매매가 비활성화되어 있습니다"}

    kis = await get_kis_client()
    if not kis.is_configured:
        return {"success": False, "error": "KIS 설정 누락 (.env의 KIS_* 값 필요)"}

    try:
        sync_result = await _reconcile_kis_domestic_symbol_to_db(kis, symbol)
    except Exception as e:
        return {"success": False, "error": f"KIS 국내/DB 수량 정합화 실패: {str(e)}"}
    if not sync_result.get("ok", False):
        return {"success": False, "error": sync_result.get("error", "KIS 국내/DB 정합화 실패")}

    async with get_session() as session:
        result = await session.execute(
            select(Position).where(
                Position.ticker == symbol,
                Position.status == PositionStatus.OPEN,
            )
        )
        open_positions = result.scalars().all()

    if not open_positions:
        logger.warning("SELL signal but no open domestic positions", ticker=symbol)
        return {
            "success": False,
            "error": f"{symbol} 보유 포지션이 없습니다",
            "ticker": symbol,
        }

    if any(_is_ib_or_legacy_position(pos) for pos in open_positions):
        return {
            "success": False,
            "error": f"{symbol} 포지션은 KIS 국내 계좌 포지션으로 확인되지 않아 매도하지 않았습니다",
        }

    total_qty = sum(float(pos.qty or 0.0) for pos in open_positions)
    if total_qty <= 0:
        return {"success": False, "error": f"{symbol} 국내 전체 매도 수량이 0입니다"}

    min_sell_limit_price = None
    if settings.sell_only_if_profit:
        balance = await kis.get_domestic_symbol_balance(symbol)
        avg_price = float(balance.get("avg_price", 0.0) or 0.0)
        if avg_price <= 0:
            total_entry_amount = sum(
                float(pos.entry_amount_usd or 0.0)
                for pos in open_positions
            )
            avg_price = (total_entry_amount / total_qty) if total_qty > 0 else 0.0

        try:
            current_price = float(await kis.get_domestic_quote_price(symbol))
        except Exception as e:
            return {
                "success": False,
                "skipped": True,
                "reason": "sell_profit_check_failed",
                "error": f"{symbol} 현재 수익률을 확인하지 못해 매도를 보류했습니다: {str(e)}",
                "ticker": symbol,
            }

        if avg_price <= 0 or current_price <= 0:
            return {
                "success": False,
                "skipped": True,
                "reason": "sell_profit_check_failed",
                "error": f"{symbol} 매수가/현재가 확인이 불완전해 매도를 보류했습니다",
                "ticker": symbol,
            }

        pnl_pct = ((current_price - avg_price) / avg_price) * 100.0
        pnl_krw = (current_price - avg_price) * total_qty
        min_profit_pct = float(settings.sell_min_profit_pct or 0.0)
        min_sell_limit_price = avg_price * (1.0 + min_profit_pct / 100.0)
        if pnl_pct < min_profit_pct:
            return {
                "success": False,
                "skipped": True,
                "reason": "sell_profit_only_hold",
                "error": (
                    f"{symbol}은 현재 손실 상태라 SELL 신호를 보류했습니다 "
                    f"(현재 수익률 {pnl_pct:+.2f}%, 평가손익 {pnl_krw:+,.0f}원). "
                    "수익 상태에서 다음 SELL 신호가 오면 매도합니다."
                ),
                "ticker": symbol,
                "pnl_pct": round(pnl_pct, 4),
                "pnl": round(pnl_krw, 2),
                "avg_price": round(avg_price, 6),
                "current_price": round(current_price, 6),
                "currency": "KRW",
            }

    try:
        order_result = await kis.place_domestic_sell_qty(
            symbol=symbol,
            qty=total_qty,
            min_limit_price=min_sell_limit_price,
        )
    except Exception as e:
        return {"success": False, "error": f"KIS 국내 매도 요청 실패: {str(e)}"}

    filled_qty = float(order_result.get("qty", 0.0) or 0.0)
    raw_order_id = str(order_result.get("order_id", "")).strip()

    if not order_result.get("success") and filled_qty <= 0:
        if order_result.get("skipped"):
            return order_result
        error_text = order_result.get("error", "KIS 국내 매도 실패")
        async with get_session() as session:
            trade = Trade(
                ticker=symbol,
                side=TradeSide.SELL,
                order_type="MKT",
                requested_qty=total_qty,
                status=TradeStatus.FAILED,
                error_message=f"KIS-KRX: {error_text}",
                alert_id=alert_id,
                position_ids=",".join(str(p.id) for p in open_positions),
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)
        return {"success": False, "error": error_text}

    fill_price = float(order_result.get("price", 0.0) or 0.0)
    if fill_price <= 0:
        fill_price = max(
            (sum(float(pos.entry_price or 0.0) * float(pos.qty or 0.0) for pos in open_positions) / total_qty)
            if total_qty > 0
            else 0.0,
            1.0,
        )
    commission = float(order_result.get("commission", 0.0) or 0.0)

    return await _apply_kis_sell_fill(
        symbol=symbol,
        requested_qty=total_qty,
        filled_qty=filled_qty,
        fill_price=fill_price,
        commission=commission,
        raw_order_id=raw_order_id,
        alert_id=alert_id,
        currency="KRW",
    )


async def _execute_sell_kis(ticker: str, alert_id: str = "") -> dict:
    """Execute SELL via KIS Open API."""
    symbol = canonical_trade_symbol(ticker)

    if is_kis_domestic_symbol(symbol):
        return await _execute_sell_kis_domestic(symbol, alert_id)

    kis = await get_kis_client()
    if not kis.is_configured:
        return {"success": False, "error": "KIS 설정 누락 (.env의 KIS_* 값 필요)"}

    try:
        sync_result = await _reconcile_kis_symbol_to_db(kis, symbol)
    except Exception as e:
        return {"success": False, "error": f"KIS/DB 수량 정합화 실패: {str(e)}"}
    if not sync_result.get("ok", False):
        return {"success": False, "error": sync_result.get("error", "KIS/DB 정합화 실패")}

    async with get_session() as session:
        result = await session.execute(
            select(Position).where(
                Position.ticker == symbol,
                Position.status == PositionStatus.OPEN,
            )
        )
        open_positions = result.scalars().all()

    if not open_positions:
        logger.warning("SELL signal but no open positions", ticker=symbol)
        return {
            "success": False,
            "error": f"{symbol} 보유 포지션이 없습니다",
            "ticker": symbol,
        }

    if any(_is_ib_or_legacy_position(pos) for pos in open_positions):
        return {
            "success": False,
            "error": f"{symbol} 포지션은 IB 계좌에 있어 KIS로 매도할 수 없습니다",
        }

    total_qty = sum(float(pos.qty or 0.0) for pos in open_positions)
    currency = _result_currency_for_symbol(symbol)
    if settings.sell_only_if_profit:
        balance = await kis.get_symbol_balance(symbol)
        avg_price = float(balance.get("avg_price", 0.0) or 0.0)
        if avg_price <= 0:
            total_entry_amount = sum(
                float(pos.entry_amount_usd or 0.0)
                for pos in open_positions
            )
            avg_price = (total_entry_amount / total_qty) if total_qty > 0 else 0.0

        try:
            current_price = float(await kis.get_quote_price(symbol))
        except Exception as e:
            return {
                "success": False,
                "skipped": True,
                "reason": "sell_profit_check_failed",
                "error": f"{symbol} 현재 수익률을 확인하지 못해 매도를 보류했습니다: {str(e)}",
                "ticker": symbol,
            }

        if avg_price <= 0 or current_price <= 0:
            return {
                "success": False,
                "skipped": True,
                "reason": "sell_profit_check_failed",
                "error": f"{symbol} 매수가/현재가 확인이 불완전해 매도를 보류했습니다",
                "ticker": symbol,
            }

        pnl_pct = ((current_price - avg_price) / avg_price) * 100.0
        pnl_native = (current_price - avg_price) * total_qty
        min_profit_pct = float(settings.sell_min_profit_pct or 0.0)
        if pnl_pct < min_profit_pct:
            return {
                "success": False,
                "skipped": True,
                "reason": "sell_profit_only_hold",
                "error": (
                    f"{symbol}은 현재 손실 상태라 SELL 신호를 보류했습니다 "
                    f"(현재 수익률 {pnl_pct:+.2f}%, 평가손익 {pnl_native:+.2f} {currency}). "
                    "수익 상태에서 다음 SELL 신호가 오면 매도합니다."
                ),
                "ticker": symbol,
                "pnl_pct": round(pnl_pct, 4),
                "pnl": round(pnl_native, 2),
                "avg_price": round(avg_price, 6),
                "current_price": round(current_price, 6),
                "currency": currency,
            }

    min_sell_limit_price = None
    if settings.sell_only_if_profit and avg_price > 0:
        min_sell_limit_price = avg_price * (1.0 + float(settings.sell_min_profit_pct or 0.0) / 100.0)

    try:
        order_result = await kis.place_sell_qty(
            symbol=symbol,
            qty=total_qty,
            min_limit_price=min_sell_limit_price,
        )
    except Exception as e:
        return {"success": False, "error": f"KIS 매도 요청 실패: {str(e)}"}

    filled_qty = float(order_result.get("qty", 0.0) or 0.0)
    raw_order_id = str(order_result.get("order_id", "")).strip()

    if not order_result.get("success") and filled_qty <= 0:
        error_text = order_result.get("error", "KIS 매도 실패")
        async with get_session() as session:
            trade = Trade(
                ticker=symbol,
                side=TradeSide.SELL,
                order_type="MKT",
                requested_qty=total_qty,
                status=TradeStatus.FAILED,
                error_message=f"KIS: {error_text}",
                alert_id=alert_id,
                position_ids=",".join(str(p.id) for p in open_positions),
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)
        return {"success": False, "error": error_text}

    fill_price = float(order_result.get("price", 0.0) or 0.0)
    if fill_price <= 0:
        fill_price = max(
            (sum(float(pos.entry_price or 0.0) * float(pos.qty or 0.0) for pos in open_positions) / total_qty)
            if total_qty > 0
            else 0.0,
            0.01,
        )
    commission = float(order_result.get("commission", 0.0) or 0.0)

    apply_result = await _apply_kis_sell_fill(
        symbol=symbol,
        requested_qty=total_qty,
        filled_qty=filled_qty,
        fill_price=fill_price,
        commission=commission,
        raw_order_id=raw_order_id,
        alert_id=alert_id,
        currency=currency,
    )
    if not apply_result.get("success"):
        return apply_result

    if order_result.get("partial_fill"):
        apply_result["partial_fill"] = True
        apply_result["partial_fill_note"] = order_result.get("error", "")

    return apply_result
