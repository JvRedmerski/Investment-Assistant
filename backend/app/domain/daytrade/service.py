"""Intraday bar ingestion (Wave 15, AGENTS.md rules 45, 47).

Its own domain package rather than a function in `market_data`, because
rule 45 keeps the day trade module apart from the long-term engine and
this is where W16's indicators and setups will live. It is still the
same *shape* as `market_data.service.sync_daily_history` - fetch,
validate, insert what is new - and deliberately so.

Two things differ from the daily path, and both come from measurement.

## A stored bar is not rewritten, and neither is a session mixed

The daily rule is "never overwrite a stored date". That rule alone is
not enough here. The vendor returns **different OHLCV for the same
instant depending on the request window**: across the same five sessions
of PETR4 15-minute bars, `5d` and `3mo` agreed on 0 of 135 bars, while
the same window asked twice agreed on 135 of 135 (ADR-036).

So "first write wins, per bar" would quietly assemble a session out of
two different partitions of that session - a series that never traded,
internally inconsistent, and undetectable afterwards. Every indicator
W16 computes on it would be wrong with nothing to show for it.

Instead a **session** is the unit that comes from one window, the same
way ADR-020 makes a fundamentals period come whole from one source. A
sync that reaches a session already stored under a different window
leaves that session completely alone and reports the conflict. Nothing
is overwritten, nothing is interleaved, and the caller is told which
sessions were refused and why.

## Awareness is restored on read, because SQLite drops it

The column is `TIMESTAMPTZ` and every value written is UTC. PostgreSQL
returns an aware datetime; SQLite, which the tests use, returns a naive
one for the same column. Comparing a naive stored value against an aware
incoming one raises `TypeError`, and - worse - would silently compare
equal-looking instants wrongly if it did not. `_as_utc` is the single
place that restores what the column already promises.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.assets import Asset, IntradayPrice
from app.integrations.market_data.base import IntradayHistoryProvider
from app.integrations.market_data.intraday_quality import (
    SessionCoverage,
    session_date,
    validate_intraday_bars,
)
from app.integrations.market_data.schemas import HistoryWindow, IntradayBar, Timeframe

logger = logging.getLogger("investment_assistant.daytrade.ingestion")


@dataclass
class WindowConflict:
    """A session this sync refused to touch, and what it disagreed with.

    Reported rather than resolved. Choosing a winner would mean either
    overwriting stored bars or discarding fetched ones, and nothing in
    the data says which partition is the right one - they are two
    self-consistent answers to the same question. Replacing a session
    is an explicit operation (`resync=true`), not a silent one.
    """

    session: date
    stored_window: HistoryWindow
    incoming_window: HistoryWindow
    bars_skipped: int


@dataclass
class IntradaySyncResult:
    ticker: str
    timeframe: Timeframe
    window: HistoryWindow
    start: datetime
    end: datetime
    fetched: int
    inserted: int
    skipped_existing: int
    rejected: int = 0
    missing_bars: int = 0
    replaced: int = 0
    sessions: list[SessionCoverage] = field(default_factory=list)
    conflicts: list[WindowConflict] = field(default_factory=list)


def sync_intraday_history(
    db: Session,
    provider: IntradayHistoryProvider,
    asset: Asset,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    *,
    resync: bool = False,
) -> IntradaySyncResult:
    """Fetch, validate and store `asset`'s intraday bars for one timeframe.

    `resync` replaces a conflicting session wholesale - every stored bar
    for that session and timeframe is deleted and the fetched window's
    bars are inserted in their place. It is the only supported way to
    move a session from one window to another, and it is whole-session
    by construction: replacing part of a session would produce exactly
    the mixture this refuses to create by accident.
    """
    history = provider.get_intraday_history(asset.ticker, timeframe, start, end)
    report = validate_intraday_bars(history.bars, timeframe)

    for issue in report.errors:
        logger.warning(
            "Rejected intraday bar for %s at %s: %s (%s)",
            asset.ticker,
            issue.at,
            issue.message,
            issue.code,
        )
    for issue in report.warnings:
        logger.info(
            "Intraday data quality warning for %s on %s: %s (%s)",
            asset.ticker,
            issue.session,
            issue.message,
            issue.code,
        )

    stored_windows, stored_stamps = _stored_state(db, asset, timeframe, start, end)

    conflicts: list[WindowConflict] = []
    replaced = 0
    inserted = 0
    skipped = 0

    by_session: dict[date, list[IntradayBar]] = {}
    for bar in report.valid_bars:
        by_session.setdefault(session_date(bar.timestamp), []).append(bar)

    for session in sorted(by_session):
        bars = by_session[session]
        stored_window = stored_windows.get(session)

        if stored_window is not None and stored_window is not history.window:
            if not resync:
                conflicts.append(
                    WindowConflict(
                        session=session,
                        stored_window=stored_window,
                        incoming_window=history.window,
                        bars_skipped=len(bars),
                    )
                )
                logger.warning(
                    "Refused to mix windows for %s on %s: stored under %s, "
                    "fetched under %s. Two windows partition a session "
                    "differently; pass resync=true to replace it.",
                    asset.ticker,
                    session,
                    stored_window.value,
                    history.window.value,
                )
                continue
            replaced += _delete_session(db, asset, timeframe, session)

        for bar in bars:
            if not resync and bar.timestamp in stored_stamps:
                skipped += 1
                continue
            db.add(
                IntradayPrice(
                    asset_id=asset.id,
                    timestamp=bar.timestamp.astimezone(UTC),
                    timeframe=timeframe.value,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=float(bar.volume),
                    source_window=history.window.value,
                    source=provider.source_name,
                )
            )
            inserted += 1

    db.commit()

    return IntradaySyncResult(
        ticker=asset.ticker,
        timeframe=timeframe,
        window=history.window,
        start=start,
        end=end,
        fetched=len(history.bars),
        inserted=inserted,
        skipped_existing=skipped,
        rejected=report.rejected_count,
        missing_bars=report.missing_bars,
        replaced=replaced,
        sessions=report.sessions,
        conflicts=conflicts,
    )


def read_intraday_bars(
    db: Session,
    asset: Asset,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> list[IntradayPrice]:
    """Stored bars for one asset and timeframe, oldest first.

    Reads only what is stored (rule 23): opening a screen never causes a
    call to the provider, which matters more here than anywhere else -
    the free plan serves intraday for only some tickers, so a read path
    that reached out would fail for reasons unrelated to the read.
    """
    rows = (
        db.execute(
            select(IntradayPrice)
            .where(
                IntradayPrice.asset_id == asset.id,
                IntradayPrice.timeframe == timeframe.value,
                IntradayPrice.timestamp >= start.astimezone(UTC),
                IntradayPrice.timestamp <= end.astimezone(UTC),
            )
            .order_by(IntradayPrice.timestamp)
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.timestamp = _as_utc(row.timestamp)
    return list(rows)


def _stored_state(
    db: Session,
    asset: Asset,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> tuple[dict[date, HistoryWindow], set[datetime]]:
    """Which window each stored session came from, and which instants exist.

    One query for both, because a sync of a month of one-minute bars
    should not cost one round trip per session.

    A session stored under two windows is impossible by construction -
    that is what this whole module prevents - but if the database ever
    held one, the first window seen wins here and the conflict is
    reported against it rather than silently averaged.
    """
    rows = db.execute(
        select(IntradayPrice.timestamp, IntradayPrice.source_window).where(
            IntradayPrice.asset_id == asset.id,
            IntradayPrice.timeframe == timeframe.value,
            IntradayPrice.timestamp >= start.astimezone(UTC),
            IntradayPrice.timestamp <= end.astimezone(UTC),
        )
    ).all()

    windows: dict[date, HistoryWindow] = {}
    stamps: set[datetime] = set()
    for stamp, window in rows:
        moment = _as_utc(stamp)
        stamps.add(moment)
        windows.setdefault(session_date(moment), HistoryWindow(window))
    return windows, stamps


def _delete_session(
    db: Session, asset: Asset, timeframe: Timeframe, session: date
) -> int:
    """Remove every stored bar of one session, for one timeframe."""
    rows = (
        db.execute(
            select(IntradayPrice).where(
                IntradayPrice.asset_id == asset.id,
                IntradayPrice.timeframe == timeframe.value,
            )
        )
        .scalars()
        .all()
    )
    removed = 0
    for row in rows:
        if session_date(_as_utc(row.timestamp)) == session:
            db.delete(row)
            removed += 1
    db.flush()
    return removed


def _as_utc(moment: datetime) -> datetime:
    """Restore the awareness the column already promises.

    Not a guess: every value written to this column is converted to UTC
    first, so a naive value coming back is a driver that dropped the
    zone (SQLite does; PostgreSQL does not), never a value that meant
    some other zone.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
