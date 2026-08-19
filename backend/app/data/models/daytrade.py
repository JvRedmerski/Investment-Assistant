from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.database import Base, utc_now


class DayTradeSetup(Base):
    __tablename__ = "daytrade_setups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # BREAKOUT, PULLBACK, VWAP
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)  # 1m, 5m, 15m
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    risk_reward: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="DETECTED", nullable=False
    )  # DETECTED, TRIGGERED, EXPIRED, CLOSED
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    asset: Mapped["Asset"] = relationship("Asset")
    result: Mapped[Optional["DayTradeResult"]] = relationship(
        "DayTradeResult",
        back_populates="setup",
        uselist=False,
        cascade="all, delete-orphan",
    )


class DayTradeResult(Base):
    __tablename__ = "daytrade_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    setup_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("daytrade_setups.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    result: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # WIN, LOSS, BREAKEVEN
    pnl: Mapped[float] = mapped_column(Float, nullable=False)
    pnl_percent: Mapped[float] = mapped_column(Float, nullable=False)
    costs: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    slippage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    setup: Mapped["DayTradeSetup"] = relationship(
        "DayTradeSetup", back_populates="result"
    )
