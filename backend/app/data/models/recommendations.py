from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.data.database import Base, utc_now


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ALLOCATION, REBALANCE, BUY, HOLD
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 0 to 100
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # Quantitative evidence score 0 to 100
    target_weight: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_amount: Mapped[float] = mapped_column(Float, nullable=False)
    horizon: Mapped[str] = mapped_column(String(20), default="LONG_TERM", nullable=False)  # SHORT_TERM, MEDIUM_TERM, LONG_TERM
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="recommendations")
    asset: Mapped["Asset"] = relationship("Asset")
