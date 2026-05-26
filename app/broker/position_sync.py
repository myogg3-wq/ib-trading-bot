"""
Position synchronization between IB and local DB.
Runs on startup and periodically to ensure consistency.
"""

from datetime import datetime, timezone
from sqlalchemy import select, func, or_
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
        return {"status": "error", "message": f"IB 연결 실패: {str(e)}"}

    # Build IB position map: symbol → total qty
    ib_map = {}
    for pos in ib_positions:
        symbol = pos["symbol"]
        ib_map[symbol] = ib_map.get(symbol, 0) + pos["qty"]

    # Build DB position map (IB scope only: legacy/IB positions).
    # KIS positions are excluded to avoid false mismatch in dual mode.
    async with get_session() as session:
        result = await session.execute(
            select(
                Position.ticker,
                func.sum(Position.qty).label("total_qty"),
            ).where(
                Position.status == PositionStatus.OPEN,
                or_(Position.entry_order_id.is_(None), Position.entry_order_id >= 0),
            ).group_by(Position.ticker)
        )
        db_positions = result.all()

        kis_excluded = await session.execute(
            select(
                func.count(Position.id).label("rows"),
                func.count(func.distinct(Position.ticker)).label("symbols"),
            ).where(
                Position.status == PositionStatus.OPEN,
                Position.entry_order_id < 0,
            )
        )
        kis_rows, kis_symbols = kis_excluded.one()

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
        "db_positions": len(db_map),  # IB-scope DB symbols
        "mismatches": mismatches,
        "scope": "IB_ONLY",
        "excluded_kis_rows": int(kis_rows or 0),
        "excluded_kis_symbols": int(kis_symbols or 0),
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
        return f"❌ 포지션 동기화 실패: {sync_result['message']}"

    msg = (
        f"🔄 포지션 동기화 리포트\n"
        f"{'─' * 30}\n"
        f"비교 범위: IB 계좌 전용\n"
        f"IB 포지션 수: {sync_result['ib_positions']}\n"
        f"DB 포지션 수: {sync_result['db_positions']}\n"
    )

    excluded_symbols = int(sync_result.get("excluded_kis_symbols", 0) or 0)
    excluded_rows = int(sync_result.get("excluded_kis_rows", 0) or 0)
    if excluded_rows > 0:
        msg += f"KIS 제외: {excluded_symbols}개 종목 / {excluded_rows}개 포지션\n"

    if sync_result["status"] == "ok":
        msg += "\n✅ 모든 포지션이 일치합니다!"
    else:
        mismatches = sync_result["mismatches"]
        msg += f"\n⚠️ 불일치 {len(mismatches)}건 발견:\n"

        for m in mismatches[:10]:
            msg += (
                f"\n{m['symbol']} ({m['type']})\n"
                f"  IB: {m['ib_qty']}, DB: {m['db_qty']}, 차이: {m['diff']:.4f}\n"
            )

        if len(mismatches) > 10:
            msg += f"\n... 외 {len(mismatches) - 10}건"

        msg += "\n\n⚠️ 수동 점검이 필요합니다."

    return msg
