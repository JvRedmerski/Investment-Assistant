from datetime import date, datetime
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
