from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.database import Base, utc_now

# Financial statement aggregates are monetary values and must not use
# float (AGENTS.md rule 17), for the same reason transactions and prices
# do not — see app.data.models.portfolio.MONEY.
#
# A wider type than MONEY (18,6) is used here because the magnitudes are
# different: statement line items are whole-company figures in the tens
# or hundreds of billions of BRL, which would consume nearly all of
# MONEY's 12 integer digits. 20 integer digits leaves ample headroom;
# 4 decimal places is more than any filing reports.
STATEMENT_MONEY = Numeric(24, 4)

# Ratios and growth rates, not currency. Float is appropriate and the
# decision is recorded here as AGENTS.md rule 17 requires.
INDICATOR = Float


class Fundamental(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (
        Index("idx_fundamentals_asset_refdate", "asset_id", "reference_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Every line item is nullable: a source may genuinely not report it.
    # NULL means "not available" and must never be read as zero.
    revenue: Mapped[Decimal | None] = mapped_column(STATEMENT_MONEY, nullable=True)
    ebitda: Mapped[Decimal | None] = mapped_column(STATEMENT_MONEY, nullable=True)
    net_income: Mapped[Decimal | None] = mapped_column(STATEMENT_MONEY, nullable=True)
    equity: Mapped[Decimal | None] = mapped_column(STATEMENT_MONEY, nullable=True)
    debt: Mapped[Decimal | None] = mapped_column(STATEMENT_MONEY, nullable=True)
    cash: Mapped[Decimal | None] = mapped_column(STATEMENT_MONEY, nullable=True)
    free_cash_flow: Mapped[Decimal | None] = mapped_column(
        STATEMENT_MONEY, nullable=True
    )
    # Added in W06-003 to unblock ROIC. `income_before_tax` and
    # `income_tax_expense` are stored as reported so the effective tax
    # rate can be derived per period, instead of assuming a headline rate
    # (ADR-014).
    ebit: Mapped[Decimal | None] = mapped_column(STATEMENT_MONEY, nullable=True)
    income_before_tax: Mapped[Decimal | None] = mapped_column(
        STATEMENT_MONEY, nullable=True
    )
    income_tax_expense: Mapped[Decimal | None] = mapped_column(
        STATEMENT_MONEY, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    asset: Mapped["Asset"] = relationship("Asset")


class FinancialIndicator(Base):
    __tablename__ = "financial_indicators"
    __table_args__ = (
        Index("idx_indicators_asset_refdate", "asset_id", "reference_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    pe: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)  # P/L
    pb: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)  # P/VP
    roe: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)
    roic: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)
    dy: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)  # Dividend Yield
    debt_ebitda: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)
    net_margin: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)
    ebitda_margin: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)
    revenue_growth: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)
    profit_growth: Mapped[float | None] = mapped_column(INDICATOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    asset: Mapped["Asset"] = relationship("Asset")
