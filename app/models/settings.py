"""
Bot settings model.
Runtime-adjustable settings stored in DB, changeable via Telegram.
"""

from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # === Trading Settings ===
    buy_amount_usd: Mapped[float] = mapped_column(Float, default=300.0, nullable=False)

    # === Risk Limits ===
    max_open_positions: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    max_daily_buys: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    max_total_investment: Mapped[float] = mapped_column(Float, default=90000.0, nullable=False)
    max_per_ticker: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_daily_loss: Mapped[float] = mapped_column(Float, default=5000.0, nullable=False)
    min_cash_reserve: Mapped[float] = mapped_column(Float, default=1000.0, nullable=False)

    # === Operation Control ===
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_killed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    regular_hours_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    queue_outside_hours: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<BotSettings(buy=${self.buy_amount_usd}, "
            f"paused={self.is_paused}, killed={self.is_killed})>"
        )

    def to_display_dict(self) -> dict:
        """Return settings in a display-friendly format for Telegram."""
        return {
            "buy_amount_usd": self.buy_amount_usd,
            "max_open_positions": self.max_open_positions,
            "max_daily_buys": self.max_daily_buys,
            "max_total_investment": self.max_total_investment,
            "max_per_ticker": self.max_per_ticker,
            "max_daily_loss": self.max_daily_loss,
            "min_cash_reserve": self.min_cash_reserve,
            "is_paused": self.is_paused,
            "is_killed": self.is_killed,
            "regular_hours_only": self.regular_hours_only,
            "queue_outside_hours": self.queue_outside_hours,
        }
