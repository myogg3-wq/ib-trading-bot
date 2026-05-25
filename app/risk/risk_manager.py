"""
Risk management module.
All pre-order checks: balance, limits, PDT, etc.
"""

from sqlalchemy import select, func, and_, or_
import structlog

from app.config import settings
from app.database.connection import get_session, get_bot_settings
from app.models.position import Position, PositionStatus
from app.models.trade import Trade, TradeSide, TradeStatus
from app.broker.ib_client import get_ib_client
from app.broker.market_hours import get_et_day_bounds_utc, get_kst_day_bounds_utc
from app.gateway.symbol_mapper import (
    parse_tv_ticker,
    is_kis_domestic_symbol,
    canonical_trade_symbol,
    kis_overseas_currency,
)

logger = structlog.get_logger()


class RiskCheckResult:
    """Result of a risk check."""

    def __init__(self, passed: bool, reason: str = ""):
        self.passed = passed
        self.reason = reason

    def __bool__(self):
        return self.passed


def _filled_trade_time_window(start_utc, end_utc):
    """
    Prefer filled_at for realized-trade day/week boundaries.
    Fallback to created_at for legacy rows with null filled_at.
    """
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


def _normalize_broker_name(value: str, fallback: str) -> str:
    name = (value or "").strip().lower()
    if name not in ("ib", "kis"):
        return fallback
    return name


def _cash_check_broker_chain() -> list[str]:
    """
    Broker chain for cash validation.
    Mirrors execution routing, but stays local to avoid cross-module coupling.
    """
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
    return ["kis"]


async def _check_ib_cash(
    buy_amount: float,
    min_reserve: float,
    needed: float,
) -> RiskCheckResult:
    try:
        ib = await get_ib_client()
        cash = await ib.get_available_cash()
    except Exception as e:
        return RiskCheckResult(False, f"현금 잔고를 확인할 수 없습니다: {str(e)}")

    if cash < needed:
        return RiskCheckResult(
            False,
            f"현금이 부족합니다. 보유: ${cash:.2f}, "
            f"필요: 매수금 ${buy_amount:.2f} + 예비금 ${min_reserve:.2f} = ${needed:.2f}",
        )
    return RiskCheckResult(True)


async def _check_kis_cash(
    buy_amount: float,
    min_reserve: float,
    ticker: str,
) -> RiskCheckResult:
    """
    KIS cash check using direct overseas buying power + integrated margin buying power.
    """
    from app.broker.kis_client import get_kis_client

    try:
        kis = await get_kis_client()
    except Exception as e:
        return RiskCheckResult(False, f"KIS 클라이언트 초기화 실패: {str(e)}")

    if not kis.is_configured:
        return RiskCheckResult(False, "KIS 설정 누락 (.env의 KIS_* 값 필요)")

    symbol = canonical_trade_symbol(ticker)
    if is_kis_domestic_symbol(symbol):
        try:
            quote_price = float(await kis.get_domestic_quote_price(symbol) or 0.0)
        except Exception as e:
            return RiskCheckResult(False, f"KIS 국내 시세 조회 실패: {str(e)}")

        if quote_price <= 0:
            return RiskCheckResult(False, f"{symbol} 국내 현재가를 확인할 수 없습니다")

        try:
            funds = await kis.get_domestic_orderable_cash(
                symbol=symbol,
                order_price=quote_price,
                ord_dvsn="01",
            )
        except Exception as e:
            return RiskCheckResult(False, f"KIS 국내 가용금 조회 실패: {str(e)}")

        target_krw = float(
            settings.kis_domestic_target_buy_krw
            or settings.kis_target_buy_krw
            or 0.0
        )
        reserve_krw = float(settings.kis_domestic_min_cash_reserve_krw or 0.0)
        needed = max(target_krw, quote_price) + reserve_krw
        available = float(
            funds.get("nrcvb_buy_amt", 0.0)
            or funds.get("ord_psbl_cash", 0.0)
            or 0.0
        )
        if available < needed:
            return RiskCheckResult(
                False,
                f"KIS 국내 현금이 부족합니다. "
                f"가용: {available:,.0f}원 / "
                f"필요: 매수기준 {max(target_krw, quote_price):,.0f}원"
                + (f" + 예비금 {reserve_krw:,.0f}원" if reserve_krw > 0 else ""),
            )
        return RiskCheckResult(True)

    quote_price = 0.0
    one_share_need = 0.0
    try:
        quote_price = float(await kis.get_quote_price(symbol) or 0.0)
        one_share_need = round(max(quote_price * 1.01, 0.01), 2)
    except Exception as e:
        logger.warning("KIS quote check failed for cash check", ticker=symbol, error=str(e))

    currency = kis_overseas_currency(symbol)
    try:
        if currency == "USD":
            funds = await kis.get_effective_usd_orderable(
                symbol=symbol or "AAPL",
                order_price=max(one_share_need, 1.0),
            )
        else:
            funds = await kis.get_effective_overseas_orderable(
                symbol=symbol,
                order_price=max(one_share_need, 1.0),
            )
    except Exception as e:
        return RiskCheckResult(False, f"KIS 가용금 조회 실패: {str(e)}")

    target_buy_usd = float(buy_amount or 0.0)
    target_krw = float(getattr(settings, "kis_target_buy_krw", 0.0) or 0.0)
    exchange_rate = float(funds.get("usd_exrt") or funds.get("exchange_rate_krw") or 0.0)
    if target_krw > 0 and exchange_rate > 0:
        target_buy_usd = target_krw / exchange_rate

    needed = max(target_buy_usd, one_share_need) + float(min_reserve or 0.0)

    available = float(funds.get("effective_usd") or funds.get("effective_local") or 0.0)
    if available < needed:
        if currency != "USD":
            return RiskCheckResult(
                False,
                f"KIS 현금이 부족합니다. "
                f"가용: {available:,.2f} {currency} / "
                f"필요: 매수기준 {max(target_buy_usd, one_share_need):,.2f} {currency}",
            )
        return RiskCheckResult(
            False,
            f"KIS 현금이 부족합니다. "
            f"가용: ${available:.2f} "
            f"(직접 ${float(funds.get('direct_ovrs_usd', 0.0)):.2f}, "
            f"통합 ${float(funds.get('integrated_usd', 0.0)):.2f}) / "
            f"필요: 매수기준 ${max(target_buy_usd, one_share_need):.2f} + "
            f"예비금 ${min_reserve:.2f} = ${needed:.2f}",
        )

    return RiskCheckResult(True)


async def check_all_buy_risks(ticker: str) -> RiskCheckResult:
    """
    Run all risk checks before executing a BUY order.
    Returns RiskCheckResult (truthy if all checks pass).
    """
    checks = [
        ("kill_switch", check_kill_switch),
        ("pause", check_pause),
        ("cash_balance", lambda t: check_cash_balance(t)),
        ("total_investment", lambda t: check_total_investment(t)),
        ("open_positions", check_open_positions),
        ("per_ticker_daily", lambda t: check_daily_buy_per_ticker_limit(t)),
        ("per_ticker", lambda t: check_per_ticker_limit(t)),
        ("daily_buys", check_daily_buy_limit),
    ]

    for check_name, check_func in checks:
        try:
            if check_name in ("per_ticker_daily", "per_ticker", "cash_balance", "total_investment"):
                result = await check_func(ticker)
            elif check_name in ("kill_switch", "pause"):
                result = await check_func()
            else:
                result = await check_func()

            if not result:
                logger.warning(
                    "Risk check failed",
                    check=check_name,
                    ticker=ticker,
                    reason=result.reason,
                )
                return result
        except Exception as e:
            logger.error("Risk check error", check=check_name, error=str(e))
            return RiskCheckResult(False, f"리스크 체크 오류 ({check_name}): {str(e)}")

    return RiskCheckResult(True)


async def check_sell_risks() -> RiskCheckResult:
    """
    Risk checks for SELL orders (minimal - we almost always want to sell).
    Only kill switch blocks sells.
    """
    return await check_kill_switch()


async def check_kill_switch() -> RiskCheckResult:
    """Check if the emergency kill switch is active."""
    bot_settings = await get_bot_settings()
    if bot_settings.is_killed:
        return RiskCheckResult(False, "긴급 정지 상태입니다. /resume 명령으로 재개할 수 있습니다.")
    return RiskCheckResult(True)


async def check_pause() -> RiskCheckResult:
    """Check if buying is paused."""
    bot_settings = await get_bot_settings()
    if bot_settings.is_paused:
        return RiskCheckResult(False, "매수 일시중지 상태입니다. /resume 명령으로 재개할 수 있습니다.")
    return RiskCheckResult(True)


async def check_cash_balance(ticker: str) -> RiskCheckResult:
    """Check if we have enough cash to buy."""
    bot_settings = await get_bot_settings()
    buy_amount = bot_settings.buy_amount_usd
    min_reserve = bot_settings.min_cash_reserve

    needed = buy_amount + min_reserve
    chain = _cash_check_broker_chain()
    failures = []

    for broker in chain:
        if broker == "ib":
            result = await _check_ib_cash(
                buy_amount=buy_amount,
                min_reserve=min_reserve,
                needed=needed,
            )
        else:
            result = await _check_kis_cash(
                buy_amount=buy_amount,
                min_reserve=min_reserve,
                ticker=ticker,
            )

        if result:
            return result
        failures.append(f"{broker.upper()}: {result.reason}")

    return RiskCheckResult(False, " / ".join(failures) if failures else "현금 검증 실패")


async def check_total_investment(ticker: str = "") -> RiskCheckResult:
    """Check if total invested amount is within limit."""
    # Existing DB amount columns are USD-named. Domestic/KRX positions store KRW
    # native amounts there, so do not mix them into the USD max-investment guard.
    if ticker and is_kis_domestic_symbol(ticker):
        return RiskCheckResult(True)

    bot_settings = await get_bot_settings()

    async with get_session() as session:
        rows = (
            await session.execute(
                select(Position.ticker, Position.entry_amount_usd).where(
                    Position.status == PositionStatus.OPEN
                )
            )
        ).all()
        total_invested = sum(
            float(amount or 0.0)
            for ticker_value, amount in rows
            if not is_kis_domestic_symbol(str(ticker_value or ""))
        )

    remaining = bot_settings.max_total_investment - total_invested
    if remaining < bot_settings.buy_amount_usd:
        return RiskCheckResult(
            False,
            f"총 투자 한도에 도달했습니다. "
            f"현재: ${total_invested:.2f} / 한도: ${bot_settings.max_total_investment:.2f}",
        )

    return RiskCheckResult(True)


async def check_open_positions() -> RiskCheckResult:
    """Check if we're under the max open positions limit."""
    bot_settings = await get_bot_settings()

    async with get_session() as session:
        result = await session.execute(
            select(func.count(Position.id)).where(
                Position.status == PositionStatus.OPEN
            )
        )
        open_count = result.scalar() or 0

    if open_count >= bot_settings.max_open_positions:
        return RiskCheckResult(
            False,
            f"최대 보유 포지션 수에 도달했습니다: {open_count}/{bot_settings.max_open_positions}",
        )

    return RiskCheckResult(True)


async def check_per_ticker_limit(ticker: str) -> RiskCheckResult:
    """Check if this ticker has too many open positions (duplicate buys)."""
    symbol = canonical_trade_symbol(ticker)
    bot_settings = await get_bot_settings()

    async with get_session() as session:
        result = await session.execute(
            select(func.count(Position.id)).where(
                Position.ticker == symbol,
                Position.status == PositionStatus.OPEN,
            )
        )
        ticker_count = result.scalar() or 0

    if ticker_count >= bot_settings.max_per_ticker:
        return RiskCheckResult(
            False,
            f"{symbol}: 종목당 최대 매수 횟수에 도달했습니다 ({ticker_count}/{bot_settings.max_per_ticker})",
        )

    return RiskCheckResult(True)


async def check_daily_buy_per_ticker_limit(ticker: str) -> RiskCheckResult:
    """
    Enforce at most one BUY fill per ticker per ET day.
    This prevents duplicate same-day buys when duplicate alerts arrive.
    """
    symbol = canonical_trade_symbol(ticker)
    if is_kis_domestic_symbol(symbol) or kis_overseas_currency(symbol) in ("HKD", "CNY", "JPY"):
        today_start, today_end = get_kst_day_bounds_utc()
    else:
        today_start, today_end = get_et_day_bounds_utc()
    max_daily_buys_per_ticker = 1

    async with get_session() as session:
        result = await session.execute(
            select(func.count(Trade.id)).where(
                Trade.ticker == symbol,
                Trade.side == TradeSide.BUY,
                Trade.status == TradeStatus.FILLED,
                _filled_trade_time_window(today_start, today_end),
            )
        )
        today_symbol_buys = result.scalar() or 0

    if today_symbol_buys >= max_daily_buys_per_ticker:
        return RiskCheckResult(
            False,
            f"{symbol}: 오늘 매수는 1회만 허용됩니다 "
            f"({today_symbol_buys}/{max_daily_buys_per_ticker})",
        )

    return RiskCheckResult(True)


async def check_daily_buy_limit() -> RiskCheckResult:
    """Check if we've exceeded today's buy limit."""
    bot_settings = await get_bot_settings()
    today_start, today_end = get_et_day_bounds_utc()

    async with get_session() as session:
        result = await session.execute(
            select(func.count(Trade.id)).where(
                Trade.side == TradeSide.BUY,
                Trade.status == TradeStatus.FILLED,
                _filled_trade_time_window(today_start, today_end),
            )
        )
        today_buys = result.scalar() or 0

    if today_buys >= bot_settings.max_daily_buys:
        return RiskCheckResult(
            False,
            f"일일 최대 매수 횟수에 도달했습니다: {today_buys}/{bot_settings.max_daily_buys}",
        )

    return RiskCheckResult(True)


async def get_risk_summary() -> dict:
    """Get current risk metrics for display (Telegram /status)."""
    bot_settings = await get_bot_settings()
    today_start, today_end = get_et_day_bounds_utc()

    async with get_session() as session:
        # Open positions count
        pos_count = (await session.execute(
            select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
        )).scalar() or 0

        # Unique tickers
        ticker_count = (await session.execute(
            select(func.count(func.distinct(Position.ticker))).where(
                Position.status == PositionStatus.OPEN
            )
        )).scalar() or 0

        # Total invested in USD symbols only. Domestic/KRX native KRW rows are
        # intentionally excluded from this legacy USD risk summary.
        invested_rows = (
            await session.execute(
                select(Position.ticker, Position.entry_amount_usd).where(
                    Position.status == PositionStatus.OPEN
                )
            )
        ).all()
        total_invested = sum(
            float(amount or 0.0)
            for ticker_value, amount in invested_rows
            if not is_kis_domestic_symbol(str(ticker_value or ""))
        )

        # Today's buys
        today_buys = (await session.execute(
            select(func.count(Trade.id)).where(
                Trade.side == TradeSide.BUY,
                Trade.status == TradeStatus.FILLED,
                _filled_trade_time_window(today_start, today_end),
            )
        )).scalar() or 0

        # Today's P&L
        today_pnl = (await session.execute(
            select(func.sum(Trade.total_pnl_usd)).where(
                Trade.side == TradeSide.SELL,
                Trade.status == TradeStatus.FILLED,
                _filled_trade_time_window(today_start, today_end),
            )
        )).scalar() or 0.0

    return {
        "open_positions": pos_count,
        "max_open_positions": bot_settings.max_open_positions,
        "unique_tickers": ticker_count,
        "total_invested": round(total_invested, 2),
        "max_investment": bot_settings.max_total_investment,
        "today_buys": today_buys,
        "max_daily_buys": bot_settings.max_daily_buys,
        "today_pnl": round(today_pnl, 2),
        "buy_amount": bot_settings.buy_amount_usd,
        "is_paused": bot_settings.is_paused,
        "is_killed": bot_settings.is_killed,
    }
