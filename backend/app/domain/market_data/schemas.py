from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator


class PriceSyncRequest(BaseModel):
    """Requested window to sync from the market data provider.

    Both bounds are optional: when omitted, the sync defaults to the last
    30 days up to today (see the route). `end` cannot be in the future and
    `start` cannot be after `end`.
    """

    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _validate_range(self) -> "PriceSyncRequest":
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start date must not be after end date.")
        # "Today" is read in UTC, explicitly, rather than from the server's
        # local clock (AGENTS.md rule 18). A future `end` is not a window the
        # provider can answer - it would quietly return whatever it has and
        # report a range that was never fetched.
        if self.end is not None and self.end > datetime.now(UTC).date():
            raise ValueError("end date must not be in the future.")
        return self


class PriceSyncResponse(BaseModel):
    """Result of a sync operation against the market data provider."""

    ticker: str
    start: date
    end: date
    fetched: int
    inserted: int
    skipped_existing: int
    rejected: int


class QuoteResponse(BaseModel):
    """The latest quote for an asset, fetched live from the provider.

    Unlike every other read path in this module, this one does call the
    external API - that is the whole point of a quote, and AGENTS.md rule
    23 targets pages that re-fetch history they already store, not an
    explicit "what is it worth right now" request. Nothing is written to
    the database: a quote is a moment, not a closed session, and storing it
    in `asset_prices` would put an intraday number where daily bars live.
    """

    ticker: str
    price: Decimal
    currency: str
    as_of: datetime


class AssetPriceResponse(BaseModel):
    """A single stored daily OHLCV bar, read from the local cache (never
    triggers a call to the external provider — see AGENTS.md rule 23).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: Decimal
    source: str
    created_at: datetime
