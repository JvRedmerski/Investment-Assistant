import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.database import Base, utc_now


class RiskProfileEnum(str, enum.Enum):
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    profile: Mapped[Optional["InvestorProfile"]] = relationship(
        "InvestorProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    portfolios: Mapped[list["Portfolio"]] = relationship(
        "Portfolio", back_populates="user", cascade="all, delete-orphan"
    )


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    risk_profile: Mapped[RiskProfileEnum] = mapped_column(
        SQLEnum(RiskProfileEnum), default=RiskProfileEnum.CONSERVATIVE, nullable=False
    )
    monthly_contribution: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("1000.00"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="profile")
