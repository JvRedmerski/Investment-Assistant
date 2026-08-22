"""Request/response contracts for the intraday data endpoints (Wave 15)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.integrations.market_data.schemas import HistoryWindow, Timeframe


class IntradayBarResponse(BaseModel):
    """One stored bar.

    `source_window` is exposed rather than kept internal because a
    caller comparing two series needs to know they came from the same
    partition of the session; two windows are not interchangeable
    (ADR-036).
    """

    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: float
    source_window: str
    source: str


class SessionCoverageResponse(BaseModel):
    """What one session delivered, and what is known to be missing in it.

    `missing_bars` counts only holes **between** delivered bars. What is
    absent before the first bar or after the last is not counted,
    because it is not measurable — see `intraday_quality`.
    """

    session: date
    bar_count: int
    first: datetime
    last: datetime
    missing_bars: int


class WindowConflictResponse(BaseModel):
    """A session left untouched because it is already stored under a
    different request window.

    Not an error: the sync succeeded for every other session. It is the
    one thing a caller must see, because the fix is a decision only they
    can make — re-sync the session under the new window, or leave it.
    """

    session: date
    stored_window: HistoryWindow
    incoming_window: HistoryWindow
    bars_skipped: int


class IntradaySyncResponse(BaseModel):
    ticker: str
    timeframe: Timeframe
    window: HistoryWindow
    start: datetime
    end: datetime
    fetched: int
    inserted: int
    skipped_existing: int
    rejected: int
    missing_bars: int
    replaced: int
    sessions: list[SessionCoverageResponse]
    conflicts: list[WindowConflictResponse]
