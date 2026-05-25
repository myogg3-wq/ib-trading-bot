"""
Reconcile KIS real holdings into local DB OPEN positions.

Usage:
    python -m scripts.reconcile_kis_positions
"""

import asyncio

from sqlalchemy import select

from app.database.connection import get_session, init_db
from app.broker.kis_client import get_kis_client
from app.broker.order_executor import _reconcile_kis_symbol_to_db
from app.models.position import Position, PositionStatus


async def reconcile_kis_positions() -> dict:
    await init_db()
    kis = await get_kis_client()
    if not kis.is_configured:
        raise RuntimeError("KIS 설정 누락 (.env의 KIS_* 값 필요)")

    rows = await kis.get_overseas_balance()
    broker_symbols = {
        str(
            row.get("ovrs_pdno")
            or row.get("pdno")
            or row.get("item_cd")
            or ""
        ).strip().upper()
        for row in rows
        if float(
            row.get("ovrs_cblc_qty")
            or row.get("cblc_qty")
            or row.get("hold_qty")
            or row.get("blce_qty")
            or 0.0
        ) > 0
    }

    async with get_session() as session:
        db_rows = (
            await session.execute(
                select(Position.ticker).where(
                    Position.status == PositionStatus.OPEN,
                    Position.entry_order_id < 0,
                )
            )
        ).all()

    db_symbols = {str(row[0]).strip().upper() for row in db_rows if row and row[0]}
    target_symbols = sorted(broker_symbols | db_symbols)

    results = []
    for symbol in target_symbols:
        result = await _reconcile_kis_symbol_to_db(kis, symbol)
        results.append((symbol, result))

    added_total = sum(float(item[1].get("added_qty", 0.0) or 0.0) for item in results if item[1].get("ok"))
    closed_total = sum(float(item[1].get("closed_qty", 0.0) or 0.0) for item in results if item[1].get("ok"))
    errors = [(symbol, result.get("error", "unknown")) for symbol, result in results if not result.get("ok")]

    return {
        "symbols_checked": len(target_symbols),
        "broker_symbols": len(broker_symbols),
        "db_symbols": len(db_symbols),
        "added_total": added_total,
        "closed_total": closed_total,
        "results": results,
        "errors": errors,
    }


async def main():
    result = await reconcile_kis_positions()
    print("KIS reconcile done")
    print(f"symbols_checked={result['symbols_checked']}")
    print(f"broker_symbols={result['broker_symbols']}")
    print(f"db_symbols={result['db_symbols']}")
    print(f"added_total={result['added_total']:.4f}")
    print(f"closed_total={result['closed_total']:.4f}")
    for symbol, item in result["results"]:
        if not item.get("ok"):
            print(f"! {symbol} error={item.get('error', 'unknown')}")
            continue
        added_qty = float(item.get("added_qty", 0.0) or 0.0)
        closed_qty = float(item.get("closed_qty", 0.0) or 0.0)
        if added_qty > 0 or closed_qty > 0:
            print(f"* {symbol} added={added_qty:.4f} closed={closed_qty:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
