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

KIS_OVERSEAS_EXCHANGE_MAP = {
    "NASDAQ": {"quote": "NAS", "order": "NASD", "currency": "USD", "region": "US"},
    "NYSE": {"quote": "NYS", "order": "NYSE", "currency": "USD", "region": "US"},
    "AMEX": {"quote": "AMS", "order": "AMEX", "currency": "USD", "region": "US"},
    "NYSEARCA": {"quote": "AMS", "order": "AMEX", "currency": "USD", "region": "US"},
    "ARCA": {"quote": "AMS", "order": "AMEX", "currency": "USD", "region": "US"},
    "HKEX": {"quote": "HKS", "order": "SEHK", "currency": "HKD", "region": "ASIA"},
    "SSE": {"quote": "SHS", "order": "SHAA", "currency": "CNY", "region": "ASIA"},
    "SZSE": {"quote": "SZS", "order": "SZAA", "currency": "CNY", "region": "ASIA"},
    "TSE": {"quote": "TSE", "order": "TKSE", "currency": "JPY", "region": "ASIA"},
}


def split_tv_ticker(tv_ticker: str) -> tuple[str, str]:
    """Return (exchange_prefix, symbol) from a TradingView ticker."""
    ticker = str(tv_ticker or "").strip().upper()
    if ":" in ticker:
        exchange_prefix, symbol = ticker.split(":", 1)
    else:
        exchange_prefix, symbol = "", ticker
    symbol = symbol.strip()
    if symbol in TICKER_MAP:
        symbol = TICKER_MAP[symbol]
    return exchange_prefix.strip(), symbol


def canonical_trade_symbol(tv_ticker: str) -> str:
    """
    Canonical symbol used by this bot for allowlist/DB/order queue identity.

    KRX symbols stay as plain codes to match the existing domestic DB shape.
    Asia overseas markets keep the exchange prefix to avoid collisions with
    Korean six-digit product codes.
    """
    exchange, symbol = split_tv_ticker(tv_ticker)
    if not symbol:
        return ""
    if exchange == "HKEX" and symbol.isdigit():
        symbol = symbol.zfill(5)
    if exchange in ("HKEX", "SSE", "SZSE", "TSE", "LSE"):
        return f"{exchange}:{symbol}"
    return symbol


def trade_symbol_code(symbol: str) -> str:
    """Return the broker-facing symbol code without a TradingView prefix."""
    _, code = split_tv_ticker(symbol)
    return code


def kis_overseas_exchange_meta(tv_ticker: str) -> dict:
    """
    Return KIS overseas quote/order/currency metadata for a TV/canonical symbol.
    Empty dict means no explicit overseas exchange prefix is known.
    """
    exchange, _ = split_tv_ticker(tv_ticker)
    if exchange == "KRX":
        return {}
    return dict(KIS_OVERSEAS_EXCHANGE_MAP.get(exchange, {}))


def kis_overseas_currency(tv_ticker: str) -> str:
    meta = kis_overseas_exchange_meta(tv_ticker)
    return str(meta.get("currency") or "USD").upper()


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
    _, symbol = split_tv_ticker(tv_ticker)

    return {
        "symbol": symbol,
        "exchange": "SMART",      # IB Smart Routing (best execution)
        "currency": "USD",        # Default to USD (US stocks)
        "sec_type": "STK",        # Stock
    }


def is_kis_domestic_symbol(tv_ticker: str) -> bool:
    """
    Return True for KIS domestic/KRX symbols.

    TradingView usually sends Korean ETFs as ``KRX:069500`` or a plain
    six-digit code. Some Korean product codes contain one letter
    (for example ``0005G0``), so allow those KRX-style codes too.
    """
    try:
        exchange, symbol = split_tv_ticker(tv_ticker)
    except Exception:
        return False
    if exchange == "KRX":
        return bool(re.fullmatch(r"[A-Z0-9]{5,7}", symbol))
    if exchange:
        return False
    if symbol.isdigit() and 5 <= len(symbol) <= 7:
        return True
    return bool(re.fullmatch(r"\d{4}[A-Z]\d", symbol))


def to_ib_contract(tv_ticker: str):
    """
    Convert TradingView ticker to IB Contract object.
    Returns an ib_insync Stock contract.

    Usage:
        contract = to_ib_contract("NASDAQ:AAPL")
        # → Stock("AAPL", "SMART", "USD")
    """
    try:
        from ib_insync import Stock
    except ImportError:
        # During testing without ib_insync installed
        logger.warning("ib_insync not installed, returning dict instead of Contract")
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
