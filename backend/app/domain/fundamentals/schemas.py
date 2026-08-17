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
