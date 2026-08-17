from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FundamentalsSyncResponse(BaseModel):
    """Result of a sync operation against the fundamentals provider."""

    ticker: str
    fetched: int
    inserted: int
    skipped_existing: int
    rejected: int


class IndicatorsComputeResponse(BaseModel):
    """Result of deriving indicators from already-stored data.

    No external provider is involved — see
    `app.domain.fundamentals.service.compute_and_store_indicators`.
    """

    ticker: str
    periods: int
    computed: int
    skipped_existing: int


class FinancialIndicatorResponse(BaseModel):
    """Derived indicators for one reference period.

    All values are fractions, not percentages (0.15 means 15%), except
    the multiples `pe`, `pb` and `debt_ebitda`, which are dimensionless.
    A `null` means the indicator was not computable from the available
    data — never zero.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    reference_date: date
    pe: float | None
    pb: float | None
    roe: float | None
    roic: float | None
    dy: float | None
    debt_ebitda: float | None
    net_margin: float | None
    ebitda_margin: float | None
    revenue_growth: float | None
    profit_growth: float | None
    created_at: datetime


class FundamentalResponse(BaseModel):
    """One stored annual financial statement, read from the local store
    (never triggers a call to the external provider — AGENTS.md rule 23).

    Any line item the source did not report is `null`, never zero.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    reference_date: date
    revenue: Decimal | None
    ebitda: Decimal | None
    net_income: Decimal | None
    equity: Decimal | None
    debt: Decimal | None
    cash: Decimal | None
    free_cash_flow: Decimal | None
    created_at: datetime
