"""
Risk management module.
All pre-order checks: balance, limits, PDT, daily loss, etc.
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
import structlog

from app.database.connection import get_session, get_bot_settings
from app.models.position import Position, PositionStatus
from app.models.trade import Trade, TradeSide, TradeStatus
from app.broker.ib_client import get_ib_client

logger = structlog.get_logger()


class RiskCheckResult:
    """Result of a risk check."""

    def __init__(self, passed: bool, reason: str = ""):
        self.passed = passed
        self.reason = reason

    def __bool__(self):
        return self.passed


async def check_all_buy_risks(ticker: str) -> RiskCheckResult:
    """
    Run all risk checks before executing a BUY order.
    Returns RiskCheckResult (truthy if all checks pass).
    """
    checks = [
        ("kill_switch", check_kill_switch),
        ("pause", check_pause),
        ("cash_balance", check_cash_balance),
        ("total_investment", check_total_investment),
        ("open_positions", check_open_positions),
        ("per_ticker", lambda t: check_per_ticker_limit(t)),
        ("daily_buys", check_daily_buy_limit),
        ("daily_loss", check_daily_loss_limit),
    ]

    for check_name, check_func in checks:
        try:
            if check_name == "per_ticker":
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
            return RiskCheckResult(False, f"Risk check error ({check_name}): {str(e)}")

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
        return RiskCheckResult(False, "Emergency kill switch is active. Use /resume to re-enable.")
    return RiskCheckResult(True)


async def check_pause() -> RiskCheckResult:
    """Check if buying is paused."""
    bot_settings = await get_bot_settings()
    if bot_settings.is_paused:
        return RiskCheckResult(False, "Buying is paused. Use /resume to re-enable.")
    return RiskCheckResult(True)


async def check_cash_balance() -> RiskCheckResult:
    """Check if we have enough cash to buy."""
    bot_settings = await get_bot_settings()
    buy_amount = bot_settings.buy_amount_usd
    min_reserve = bot_settings.min_cash_reserve

    try:
        ib = await get_ib_client()
        cash = await ib.get_available_cash()
    except Exception as e:
        return RiskCheckResult(False, f"Cannot check cash balance: {str(e)}")

    needed = buy_amount + min_reserve
    if cash < needed:
        return RiskCheckResult(
            False,
            f"Insufficient cash. Available: ${cash:.2f}, "
            f"Need: ${buy_amount:.2f} + ${min_reserve:.2f} reserve = ${needed:.2f}",
        )

    return RiskCheckResult(True)


async def check_total_investment() -> RiskCheckResult:
    """Check if total invested amount is within limit."""
    bot_settings = await get_bot_settings()

    async with get_session() as session:
        result = await session.execute(
            select(func.sum(Position.entry_amount_usd)).where(
                Position.status == PositionStatus.OPEN
            )
        )
        total_invested = result.scalar() or 0.0

    remaining = bot_settings.max_total_investment - total_invested
    if remaining < bot_settings.buy_amount_usd:
        return RiskCheckResult(
            False,
            f"Total investment limit reached. "
            f"Invested: ${total_invested:.2f} / ${bot_settings.max_total_investment:.2f}",
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
            f"Max open positions reached: {open_count}/{bot_settings.max_open_positions}",
        )

    return RiskCheckResult(True)


async def check_per_ticker_limit(ticker: str) -> RiskCheckResult:
    """Check if this ticker has too many open positions (duplicate buys)."""
    from app.gateway.symbol_mapper import parse_tv_ticker
    symbol = parse_tv_ticker(ticker)["symbol"]
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
            f"{symbol}: max duplicate buys reached ({ticker_count}/{bot_settings.max_per_ticker})",
        )

    return RiskCheckResult(True)


async def check_daily_buy_limit() -> RiskCheckResult:
    """Check if we've exceeded today's buy limit."""
    bot_settings = await get_bot_settings()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_session() as session:
        result = await session.execute(
            select(func.count(Trade.id)).where(
                Trade.side == TradeSide.BUY,
                Trade.status == TradeStatus.FILLED,
                Trade.created_at >= today_start,
            )
        )
        today_buys = result.scalar() or 0

    if today_buys >= bot_settings.max_daily_buys:
        return RiskCheckResult(
            False,
            f"Daily buy limit reached: {today_buys}/{bot_settings.max_daily_buys}",
        )

    return RiskCheckResult(True)


async def check_daily_loss_limit() -> RiskCheckResult:
    """Check if today's total realized loss exceeds limit."""
    bot_settings = await get_bot_settings()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_session() as session:
        result = await session.execute(
            select(func.sum(Trade.total_pnl_usd)).where(
                Trade.side == TradeSide.SELL,
                Trade.status == TradeStatus.FILLED,
                Trade.created_at >= today_start,
                Trade.total_pnl_usd < 0,  # Only losses
            )
        )
        today_loss = abs(result.scalar() or 0.0)

    if today_loss >= bot_settings.max_daily_loss:
        return RiskCheckResult(
            False,
            f"Daily loss limit reached: -${today_loss:.2f} / -${bot_settings.max_daily_loss:.2f}",
        )

    return RiskCheckResult(True)


async def get_risk_summary() -> dict:
    """Get current risk metrics for display (Telegram /status)."""
    bot_settings = await get_bot_settings()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

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

        # Total invested
        total_invested = (await session.execute(
            select(func.sum(Position.entry_amount_usd)).where(
                Position.status == PositionStatus.OPEN
            )
        )).scalar() or 0.0

        # Today's buys
        today_buys = (await session.execute(
            select(func.count(Trade.id)).where(
                Trade.side == TradeSide.BUY,
                Trade.status == TradeStatus.FILLED,
                Trade.created_at >= today_start,
            )
        )).scalar() or 0

        # Today's P&L
        today_pnl = (await session.execute(
            select(func.sum(Trade.total_pnl_usd)).where(
                Trade.side == TradeSide.SELL,
                Trade.status == TradeStatus.FILLED,
                Trade.created_at >= today_start,
            )
        )).scalar() or 0.0

    return {
        "open_positions": pos_count,
        "unique_tickers": ticker_count,
        "total_invested": round(total_invested, 2),
        "max_investment": bot_settings.max_total_investment,
        "today_buys": today_buys,
        "max_daily_buys": bot_settings.max_daily_buys,
        "today_pnl": round(today_pnl, 2),
        "max_daily_loss": bot_settings.max_daily_loss,
        "buy_amount": bot_settings.buy_amount_usd,
        "is_paused": bot_settings.is_paused,
        "is_killed": bot_settings.is_killed,
    }
