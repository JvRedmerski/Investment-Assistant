from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import String, Integer, Float, Date, DateTime, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.data.database import Base, utc_now


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)  # STOCK, FII, ETF, FIXED_INCOME, BDR
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="BRL", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    prices: Mapped[List["AssetPrice"]] = relationship("AssetPrice", back_populates="asset", cascade="all, delete-orphan")
    intraday_prices: Mapped[List["IntradayPrice"]] = relationship("IntradayPrice", back_populates="asset", cascade="all, delete-orphan")


class AssetPrice(Base):
    __tablename__ = "asset_prices"
    __table_args__ = (
        UniqueConstraint("asset_id", "date", name="uq_asset_price_date"),
        Index("idx_asset_price_date", "asset_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    adjusted_close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="brapi", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="prices")


class IntradayPrice(Base):
    __tablename__ = "intraday_prices"
    __table_args__ = (
        UniqueConstraint("asset_id", "timestamp", "timeframe", name="uq_intraday_timestamp_timeframe"),
        Index("idx_intraday_asset_timestamp", "asset_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)  # 1m, 5m, 15m
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="intraday_provider", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="intraday_prices")
