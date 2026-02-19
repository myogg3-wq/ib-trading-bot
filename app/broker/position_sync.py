"""
Position synchronization between IB and local DB.
Runs on startup and periodically to ensure consistency.
"""

from datetime import datetime, timezone
from sqlalchemy import select, func
import structlog

from app.database.connection import get_session
from app.models.position import Position, PositionStatus
from app.broker.ib_client import get_ib_client

logger = structlog.get_logger()


async def sync_positions() -> dict:
    """
    Synchronize positions between IB and local database.

    Compares IB actual holdings with DB records and reports discrepancies.
    Does NOT auto-correct (too risky) — reports mismatches for review.

    Returns dict with sync results.
    """
    logger.info("Starting position synchronization...")

    try:
        ib = await get_ib_client()
        ib_positions = await ib.get_positions()
    except Exception as e:
        logger.error("Cannot sync: IB connection failed", error=str(e))
        return {"status": "error", "message": f"IB connection failed: {str(e)}"}

    # Build IB position map: symbol → total qty
    ib_map = {}
    for pos in ib_positions:
        symbol = pos["symbol"]
        ib_map[symbol] = ib_map.get(symbol, 0) + pos["qty"]

    # Build DB position map
    async with get_session() as session:
        result = await session.execute(
            select(
                Position.ticker,
                func.sum(Position.qty).label("total_qty"),
            ).where(
                Position.status == PositionStatus.OPEN
            ).group_by(Position.ticker)
        )
        db_positions = result.all()

    db_map = {row[0]: float(row[1]) for row in db_positions}

    # Compare
    mismatches = []
    all_symbols = set(list(ib_map.keys()) + list(db_map.keys()))

    for symbol in all_symbols:
        ib_qty = ib_map.get(symbol, 0)
        db_qty = db_map.get(symbol, 0)

        # Allow small floating point differences
        if abs(ib_qty - db_qty) > 0.001:
            mismatches.append({
                "symbol": symbol,
                "ib_qty": ib_qty,
                "db_qty": db_qty,
                "diff": ib_qty - db_qty,
                "type": (
                    "IB_ONLY" if db_qty == 0
                    else "DB_ONLY" if ib_qty == 0
                    else "QTY_MISMATCH"
                ),
            })

    result = {
        "status": "ok" if not mismatches else "mismatch",
        "ib_positions": len(ib_map),
        "db_positions": len(db_map),
        "mismatches": mismatches,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }

    if mismatches:
        logger.warning(
            "Position sync found mismatches",
            count=len(mismatches),
            mismatches=mismatches,
        )
    else:
        logger.info(
            "Position sync complete — no mismatches",
            ib_count=len(ib_map),
            db_count=len(db_map),
        )

    return result


def format_sync_report(sync_result: dict) -> str:
    """Format sync result for Telegram display."""
    if sync_result["status"] == "error":
        return f"❌ Sync failed: {sync_result['message']}"

    msg = (
        f"🔄 Position Sync Report\n"
        f"{'─' * 30}\n"
        f"IB positions: {sync_result['ib_positions']}\n"
        f"DB positions: {sync_result['db_positions']}\n"
    )

    if sync_result["status"] == "ok":
        msg += "\n✅ All positions match!"
    else:
        mismatches = sync_result["mismatches"]
        msg += f"\n⚠️ {len(mismatches)} mismatches found:\n"

        for m in mismatches[:10]:
            msg += (
                f"\n{m['symbol']} ({m['type']})\n"
                f"  IB: {m['ib_qty']}, DB: {m['db_qty']}, Diff: {m['diff']:.4f}\n"
            )

        if len(mismatches) > 10:
            msg += f"\n... and {len(mismatches) - 10} more"

        msg += "\n\n⚠️ Please review manually!"

    return msg
