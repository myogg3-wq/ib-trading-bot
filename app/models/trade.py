"""
Trade model.
Records every individual order execution for audit trail.
"""

from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.models.base import Base


class TradeSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, enum.Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Order info
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[TradeSide] = mapped_column(SAEnum(TradeSide), nullable=False)
    order_type: Mapped[str] = mapped_column(String(10), default="MKT", nullable=False)

    # Execution details
    requested_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    requested_amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_fill_amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission: Mapped[float | None] = mapped_column(Float, nullable=True)

    # IB references
    ib_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ib_perm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Status
    status: Mapped[TradeStatus] = mapped_column(
        SAEnum(TradeStatus), default=TradeStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Linked positions (for SELL, comma-separated position IDs)
    position_ids: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # P&L (for SELL trades)
    total_pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Alert reference
    alert_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_trades_ticker_side", "ticker", "side"),
        Index("ix_trades_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, {self.side} {self.ticker}, "
            f"qty={self.filled_qty}, status={self.status})>"
        )
