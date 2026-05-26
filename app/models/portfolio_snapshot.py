"""
Portfolio snapshot model.
Stores daily KIS balance summary values for balance/equity trend reporting.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    broker: Mapped[str] = mapped_column(String(20), nullable=False, default="KIS")

    total_asset_krw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    purchase_amount_krw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cash_krw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    today_eval_pnl_krw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    today_eval_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("snapshot_date", "broker", name="uq_portfolio_snapshots_date_broker"),
        Index("ix_portfolio_snapshots_date_broker", "snapshot_date", "broker"),
    )

    def __repr__(self) -> str:
        return (
            f"<PortfolioSnapshot(date={self.snapshot_date}, broker={self.broker}, "
            f"asset_krw={self.total_asset_krw:,.0f}, eval_pnl_krw={self.today_eval_pnl_krw:,.0f})>"
        )
