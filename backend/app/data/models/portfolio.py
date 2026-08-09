from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from app.data.database import Base, utc_now


class TransactionTypeEnum(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="portfolios")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="portfolio", cascade="all, delete-orphan")
    snapshots: Mapped[List["PortfolioSnapshot"]] = relationship("PortfolioSnapshot", back_populates="portfolio", cascade="all, delete-orphan")
    recommendations: Mapped[List["Recommendation"]] = relationship("Recommendation", back_populates="portfolio", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_transactions_portfolio_asset", "portfolio_id", "asset_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[TransactionTypeEnum] = mapped_column(SQLEnum(TransactionTypeEnum), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fees: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="transactions")
    asset: Mapped[Optional["Asset"]] = relationship("Asset")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("idx_snapshot_portfolio_date", "portfolio_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    cash_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    return_daily: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    return_monthly: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    return_ytd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    return_yearly: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="snapshots")
