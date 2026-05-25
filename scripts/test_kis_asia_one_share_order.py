#!/usr/bin/env python3
"""Dry-run or execute a one-share KIS Asia-market order during market hours."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.broker.kis_client import get_kis_client
from app.broker.market_hours import is_market_open_for_ticker
from app.gateway.symbol_mapper import kis_overseas_currency, split_tv_ticker


ASIA_EXCHANGES = {"HKEX", "SSE", "SZSE", "TSE"}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", nargs="?", default="TSE:213A", help="Asia ticker, e.g. TSE:213A or HKEX:03193")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--execute", action="store_true", help="Actually send the one-share order")
    parser.add_argument("--ignore-market-hours", action="store_true", help="Allow execution even when local market check says closed")
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()
    exchange, _ = split_tv_ticker(ticker)
    if exchange not in ASIA_EXCHANGES:
        print(f"ERROR: Asia ticker only. Got {ticker}")
        return 2

    kis = await get_kis_client()
    if not kis.is_configured:
        print("ERROR: KIS is not configured")
        return 2

    quote = await kis.get_quote_snapshot(ticker)
    price = float(quote.get("price") or 0.0)
    currency = str(quote.get("currency") or kis_overseas_currency(ticker) or "").upper()
    market_open = is_market_open_for_ticker(ticker)

    print(f"ticker={ticker}")
    print(f"exchange={exchange}")
    print(f"price={price} {currency}")
    print(f"market_open={market_open}")
    print("qty=1")

    if not args.execute:
        print("dry_run=true")
        print("To execute during market hours, rerun with --execute")
        return 0

    if not market_open and not args.ignore_market_hours:
        print("ERROR: market is closed; not sending live order")
        return 3

    result = await kis.place_market_order(ticker, args.side, 1, limit_price=price)
    print(f"order_id={result.get('order_id') or '-'}")
    print("sent=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
