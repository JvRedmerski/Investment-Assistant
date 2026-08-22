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


class IntradaySeriesResponse(BaseModel):
    """Stored bars, and which partitions they came from.

    An envelope rather than a bare list — unlike `GET /{ticker}/prices`,
    which returns daily bars and needs none. The difference is measured,
    not stylistic: a daily bar is the same bar whoever asks, while an
    intraday series assembled over time can hold sessions fetched under
    different request windows, and those windows partition a session
    differently (ADR-036).

    Ingestion guarantees that **no single session** mixes windows. It
    cannot guarantee that a multi-session series is homogeneous: syncing
    three days and then sixty leaves the first three sessions under `5d`
    and the rest under `3mo`, which is exactly what a real run produced.
    Every bar carries its own `source_window`, but a caller should not
    have to scan for that, so `windows` states it once. More than one
    entry means any calculation that crosses a session boundary — an EMA
    spanning days, say — is reading across a seam.

    Re-syncing the whole range with `resync=true` is what collapses it
    back to one window.
    """

    ticker: str
    timeframe: Timeframe
    #: Every request window represented in `bars`, sorted. One entry is a
    #: homogeneous series; more than one is a seam the caller must know
    #: about.
    windows: list[HistoryWindow]
    session_count: int
    bars: list[IntradayBarResponse]
