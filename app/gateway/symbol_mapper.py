"""
TradingView ticker → IB Contract mapper.
Handles various TV ticker formats and converts to IB-compatible contracts.
"""

import re
import structlog

logger = structlog.get_logger()

# Special ticker mappings (TV symbol → IB symbol)
TICKER_MAP = {
    "BRK.B": "BRK B",
    "BRK.A": "BRK A",
    "BF.B": "BF B",
    "BF.A": "BF A",
}


def parse_tv_ticker(tv_ticker: str) -> dict:
    """
    Parse TradingView ticker into components.

    Input formats:
      "AAPL"           → symbol=AAPL, exchange=SMART
      "NASDAQ:AAPL"    → symbol=AAPL, exchange=SMART (we use SMART routing)
      "NYSE:BRK.B"     → symbol=BRK B, exchange=SMART
      "AMEX:SPY"       → symbol=SPY, exchange=SMART

    Returns dict with: symbol, exchange, currency, sec_type
    """
    ticker = tv_ticker.strip().upper()

    # Remove exchange prefix if present
    if ":" in ticker:
        exchange_prefix, symbol = ticker.split(":", 1)
    else:
        symbol = ticker

    # Apply special mappings
    if symbol in TICKER_MAP:
        symbol = TICKER_MAP[symbol]

    # Remove any trailing whitespace or special chars
    symbol = symbol.strip()

    return {
        "symbol": symbol,
        "exchange": "SMART",      # IB Smart Routing (best execution)
        "currency": "USD",        # Default to USD (US stocks)
        "sec_type": "STK",        # Stock
    }


def to_ib_contract(tv_ticker: str):
    """
    Convert TradingView ticker to IB Contract object.
    Returns an ib_async Stock contract.

    Usage:
        contract = to_ib_contract("NASDAQ:AAPL")
        # → Stock("AAPL", "SMART", "USD")
    """
    try:
        from ib_async import Stock
    except ImportError:
        # During testing without ib_async installed
        logger.warning("ib_async not installed, returning dict instead of Contract")
        return parse_tv_ticker(tv_ticker)

    parsed = parse_tv_ticker(tv_ticker)

    contract = Stock(
        symbol=parsed["symbol"],
        exchange=parsed["exchange"],
        currency=parsed["currency"],
    )

    logger.debug(
        "Mapped TV ticker to IB contract",
        tv_ticker=tv_ticker,
        ib_symbol=parsed["symbol"],
    )

    return contract


def validate_ticker(tv_ticker: str) -> bool:
    """
    Basic validation of ticker format.
    Returns True if the ticker looks valid.
    """
    if not tv_ticker or not tv_ticker.strip():
        return False

    # Remove exchange prefix
    ticker = tv_ticker.split(":")[-1].strip()

    # Check reasonable length (1-10 chars)
    if len(ticker) < 1 or len(ticker) > 10:
        return False

    # Allow letters, dots, spaces (for BRK.B → BRK B)
    if not re.match(r'^[A-Za-z0-9.\- ]+$', ticker):
        return False

    return True
