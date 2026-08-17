import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.database import Base, utc_now

# Precision used for monetary/quantity columns (AGENTS.md rule 17: never use
# float indiscriminately for critical monetary values). 18 total digits with
# 6 decimal places accommodates fractional share quantities (e.g. FIIs/ETFs
# fractional market) and BRL prices without silent rounding drift.
MONEY = Numeric(18, 6)


class TransactionTypeEnum(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="portfolios")
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="portfolio", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["PortfolioSnapshot"]] = relationship(
        "PortfolioSnapshot", back_populates="portfolio", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        "Recommendation", back_populates="portfolio", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_transactions_portfolio_asset", "portfolio_id", "asset_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[TransactionTypeEnum] = mapped_column(
        SQLEnum(TransactionTypeEnum), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), nullable=False)
    price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), nullable=False)
    fees: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio", back_populates="transactions"
    )
    asset: Mapped[Optional["Asset"]] = relationship("Asset")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (Index("idx_snapshot_portfolio_date", "portfolio_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    cash_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    return_daily: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_monthly: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_ytd: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_yearly: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio", back_populates="snapshots"
    )
