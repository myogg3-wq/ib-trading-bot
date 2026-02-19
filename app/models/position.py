"""
Position model.
Each BUY creates a new row. SELL closes ALL rows for that ticker.
Supports multiple positions per ticker (duplicate buys).
"""

from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.models.base import Base


class PositionStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ticker info
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Entry details
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_amount_usd: Mapped[float] = mapped_column(Float, nullable=False)  # actual $ spent
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Exit details (filled on SELL)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # P&L (filled on SELL)
    pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Status
    status: Mapped[PositionStatus] = mapped_column(
        SAEnum(PositionStatus), default=PositionStatus.OPEN, nullable=False, index=True
    )

    # IB order IDs
    entry_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_positions_ticker_status", "ticker", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Position(id={self.id}, ticker={self.ticker}, qty={self.qty}, "
            f"entry={self.entry_price}, status={self.status})>"
        )
