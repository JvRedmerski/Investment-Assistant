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


class PriceBackfillRequest(BaseModel):
    """Requested window to backfill from the open historical archive.

    Unlike `PriceSyncRequest` there is no plan ceiling to respect: the
    source is one file per calendar year, published openly, so the only
    cost of a wide window is download time and disk. `start` defaults to
    the configured first year.
    """

    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _validate_range(self) -> "PriceBackfillRequest":
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start date must not be after end date.")
        if self.end is not None and self.end > datetime.now(UTC).date():
            raise ValueError("end date must not be in the future.")
        return self


class CorporateActionSyncRequest(BaseModel):
    """Requested window of corporate actions to ingest.

    The window filters on the action's **last date prior** — B3's own
    date — not on the ex-date it resolves to, so an action whose data-com
    falls on the last day of the window is still fetched even though it
    goes ex the session after.
    """

    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _validate_range(self) -> "CorporateActionSyncRequest":
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start date must not be after end date.")
        if self.end is not None and self.end > datetime.now(UTC).date():
            raise ValueError("end date must not be in the future.")
        return self


class CorporateActionSyncResponse(BaseModel):
    """Result of ingesting corporate actions and rebuilding adjusted closes.

    The absence fields carry the answer to "why is this asset's risk
    still missing", which is otherwise invisible: `unaccounted` lists the
    sessions B3's own archive counted ex and that no published action
    sizes, and the most recent of those is exactly why
    `first_adjustable` is where it is.
    """

    ticker: str
    start: date
    end: date
    fetched: int
    inserted: int
    skipped_existing: int
    unplaced: int
    unaccounted: list[date]
    unusable: list[date]
    adjusted_written: int
    first_adjustable: date | None
    last_adjustable: date | None


class CorporateActionResponse(BaseModel):
    """One stored corporate action, read from the local cache.

    Exactly one of `cash_amount` (reais per share) and `share_ratio`
    (shares after per share before) is set, and which one is implied by
    `kind`. The other is `None` rather than zero or one, because a
    neutral-looking number in an empty slot is indistinguishable from a
    measured one.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    ex_date: date
    last_date_prior: date
    kind: str
    cash_amount: Decimal | None
    share_ratio: Decimal | None
    label: str
    source: str
    created_at: datetime


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
    # `None` when the source that supplied the bar publishes no
    # adjusted close - B3's COTAHIST prints traded prices (ADR-023).
    # `source` says which one it was.
    adjusted_close: Decimal | None
    volume: Decimal
    source: str
    created_at: datetime
