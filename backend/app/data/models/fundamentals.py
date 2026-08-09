from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.data.database import Base, utc_now


class Fundamental(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (
        Index("idx_fundamentals_asset_refdate", "asset_id", "reference_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ebitda: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    debt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cash: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    free_cash_flow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset")


class FinancialIndicator(Base):
    __tablename__ = "financial_indicators"
    __table_args__ = (
        Index("idx_indicators_asset_refdate", "asset_id", "reference_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    pe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # P/L
    pb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # P/VP
    roe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roic: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Dividend Yield
    debt_ebitda: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ebitda_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_growth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_growth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset")
