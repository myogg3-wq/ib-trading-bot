"""
Order execution logic.
BUY: $N market order (configurable via Telegram)
SELL: 100% market sell of all positions for the ticker
"""

from datetime import datetime, timezone
from typing import Optional
import structlog

from app.broker.ib_client import get_ib_client
from app.broker.market_hours import is_market_open
from app.gateway.symbol_mapper import to_ib_contract, parse_tv_ticker
from app.database.connection import get_session, get_bot_settings
from app.models.position import Position, PositionStatus
from app.models.trade import Trade, TradeSide, TradeStatus

logger = structlog.get_logger()


async def execute_buy(ticker: str, alert_id: str = "") -> dict:
    """
    Execute a BUY order for $N worth of a ticker (market order).

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
            return {"success": False, "error": f"Could not qualify contract for {ticker}"}
        contract = qualified[0]
    except Exception as e:
        return {"success": False, "error": f"Contract qualification failed: {str(e)}"}

    # Get current price
    price = await ib.get_snapshot_price(contract)
    if not price or price <= 0:
        return {"success": False, "error": f"Could not get price for {ticker}"}

    # Calculate quantity
    quantity = round(buy_amount / price, 4)
    if quantity <= 0:
        return {"success": False, "error": f"Calculated quantity is 0 for {ticker} at ${price}"}

    # Place market order
    try:
        order_result = await ib.place_market_order(contract, "BUY", quantity)
    except Exception as e:
        return {"success": False, "error": f"Order placement failed: {str(e)}"}

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
                error_message=f"Order status: {order_result['status']}",
                alert_id=alert_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)

        return {
            "success": False,
            "error": f"Order not filled. Status: {order_result['status']}",
            "order_id": order_result.get("order_id"),
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
        "ticker": symbol,
        "qty": fill_qty,
        "price": fill_price,
        "amount": round(fill_amount, 2),
        "commission": order_result.get("commission", 0),
        "order_id": order_result["order_id"],
    }


async def execute_sell(ticker: str, alert_id: str = "") -> dict:
    """
    Execute a SELL order: 100% of all positions for this ticker (market order).

    Steps:
    1. Look up all OPEN positions for this ticker in DB
    2. Sum total quantity
    3. Place single market sell order for total quantity
    4. Close all positions and record P&L
    """
    symbol = parse_tv_ticker(ticker)["symbol"]

    # Get all open positions for this ticker
    from sqlalchemy import select
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
            "error": f"No open positions for {symbol}",
            "ticker": symbol,
        }

    # Calculate total quantity to sell
    total_qty = sum(pos.qty for pos in open_positions)
    total_entry_amount = sum(pos.entry_amount_usd for pos in open_positions)
    position_count = len(open_positions)

    if total_qty <= 0:
        return {"success": False, "error": f"Total quantity is 0 for {symbol}"}

    # Connect to IB and place sell order
    ib = await get_ib_client()
    contract = to_ib_contract(ticker)

    try:
        qualified = await ib.ib.qualifyContractsAsync(contract)
        if qualified:
            contract = qualified[0]
    except Exception as e:
        return {"success": False, "error": f"Contract qualification failed: {str(e)}"}

    try:
        order_result = await ib.place_market_order(contract, "SELL", total_qty)
    except Exception as e:
        return {"success": False, "error": f"Sell order placement failed: {str(e)}"}

    if not order_result["filled"]:
        async with get_session() as session:
            trade = Trade(
                ticker=symbol,
                side=TradeSide.SELL,
                order_type="MKT",
                requested_qty=total_qty,
                ib_order_id=order_result.get("order_id"),
                status=TradeStatus.FAILED,
                error_message=f"Order status: {order_result['status']}",
                alert_id=alert_id,
                position_ids=",".join(str(p.id) for p in open_positions),
                created_at=datetime.now(timezone.utc),
            )
            session.add(trade)

        return {
            "success": False,
            "error": f"Sell order not filled. Status: {order_result['status']}",
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
        positions_to_close = result.scalars().all()

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
