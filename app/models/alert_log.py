"""
Alert log model.
Records every incoming webhook alert for debugging and audit.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Alert content
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY or SELL
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alert_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Raw payload for debugging
    raw_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Source info
    source_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Processing status
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    queued: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    skip_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Timing
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )

    def __repr__(self) -> str:
        return f"<AlertLog(id={self.id}, {self.action} {self.ticker}, processed={self.processed})>"
