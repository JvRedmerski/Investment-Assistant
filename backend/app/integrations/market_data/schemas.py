"""Data transfer objects returned by a `MarketDataProvider`.

These are provider-agnostic: nothing here (or in `base.py`) knows about
Brapi. Using Pydantic gives free type validation/coercion for data coming
from an external, untrusted source (AGENTS.md rule 19 — never assume a
field exists or is well-formed).
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class DailyBar(BaseModel):
    """One OHLCV daily bar for an asset.

    `adjusted_close` is `None` when the source did not report one. It is
    deliberately not defaulted to `close`: the adjusted close is a
    different quantity (it nets out dividends and splits), so filling it
    from the raw close would substitute a fabricated figure for a missing
    one — what AGENTS.md rule 44 and ADR-014 forbid. `validate_daily_bars`
    rejects such bars, so nothing unadjusted reaches storage.
    """

    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal | None
    volume: Decimal = Field(ge=0)


class Quote(BaseModel):
    """A single latest-price quote for an asset."""

    ticker: str
    price: Decimal
    currency: str
    as_of: datetime
