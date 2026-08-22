"""Intraday ingestion (W15-005), against a fake provider and in-memory SQLite.

The interesting half of this file is the window conflict. The daily
path's rule - never overwrite a stored date - is not enough for intraday,
because the same instant comes back with different OHLCV depending on
which range window served it. First-write-wins per bar would quietly
assemble a session out of two partitions of that session.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset, IntradayPrice
from app.domain.daytrade.service import read_intraday_bars, sync_intraday_history
from app.integrations.market_data.base import IntradayHistory, IntradayHistoryProvider
from app.integrations.market_data.intraday_quality import EXCHANGE_TIMEZONE
from app.integrations.market_data.schemas import (
    HistoryWindow,
    IntradayBar,
    Timeframe,
)

_15M = Timeframe.FIFTEEN_MINUTES


class FakeIntradayProvider(IntradayHistoryProvider):
    source_name = "fake"

    def __init__(self, history: IntradayHistory):
        self._history = history
        self.calls = 0

    def get_intraday_history(self, ticker, timeframe, start, end):
        self.calls += 1
        return IntradayHistory(
            timeframe=self._history.timeframe,
            window=self._history.window,
            bars=[b for b in self._history.bars if start <= b.timestamp <= end],
        )


def _local(day: date, hour: int, minute: int) -> datetime:
    return datetime(
        day.year, day.month, day.day, hour, minute, tzinfo=EXCHANGE_TIMEZONE
    )


def _bar(moment: datetime, close: str = "42.00", volume: str = "1000") -> IntradayBar:
    price = Decimal(close)
    return IntradayBar(
        timestamp=moment,
        timeframe=_15M,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal(volume),
    )


def _session_bars(day: date, count: int = 4, close: str = "42.00") -> list[IntradayBar]:
    first = _local(day, 10, 15)
    return [_bar(first + timedelta(minutes=15 * i), close=close) for i in range(count)]


def _history(bars, window=HistoryWindow.FIVE_DAYS) -> IntradayHistory:
    return IntradayHistory(timeframe=_15M, window=window, bars=bars)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def asset(db_session):
    asset = Asset(ticker="PETR4", name="Petrobras PN", asset_type="STOCK")
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


_WINDOW = (
    datetime(2026, 8, 17, tzinfo=UTC),
    datetime(2026, 8, 22, tzinfo=UTC),
)


def _sync(db, asset, history, **kwargs):
    return sync_intraday_history(
        db, FakeIntradayProvider(history), asset, _15M, *_WINDOW, **kwargs
    )


class TestInsertion:
    def test_bars_are_stored_with_their_window(self, db_session, asset):
        result = _sync(db_session, asset, _history(_session_bars(date(2026, 8, 18))))

        assert result.fetched == 4
        assert result.inserted == 4
        assert result.window is HistoryWindow.FIVE_DAYS

        stored = db_session.query(IntradayPrice).all()
        assert len(stored) == 4
        assert {row.source_window for row in stored} == {"5d"}
        assert {row.timeframe for row in stored} == {"15m"}
        assert {row.source for row in stored} == {"fake"}

    def test_prices_survive_as_decimals(self, db_session, asset):
        _sync(
            db_session,
            asset,
            _history([_bar(_local(date(2026, 8, 18), 10, 15), close="42.91")]),
        )
        stored = db_session.query(IntradayPrice).one()
        assert stored.close == Decimal("42.91")

    def test_the_stored_instant_is_utc(self, db_session, asset):
        """Written local, stored UTC: 10:15 in B3's session is 13:15 UTC."""
        _sync(db_session, asset, _history([_bar(_local(date(2026, 8, 18), 10, 15))]))
        stored = db_session.query(IntradayPrice).one()
        assert (stored.timestamp.hour, stored.timestamp.minute) == (13, 15)

    def test_a_second_sync_of_the_same_window_inserts_nothing(self, db_session, asset):
        bars = _session_bars(date(2026, 8, 18))
        _sync(db_session, asset, _history(bars))
        result = _sync(db_session, asset, _history(bars))

        assert result.inserted == 0
        assert result.skipped_existing == 4
        assert db_session.query(IntradayPrice).count() == 4

    def test_new_bars_of_a_stored_session_are_appended(self, db_session, asset):
        day = date(2026, 8, 18)
        _sync(db_session, asset, _history(_session_bars(day, count=2)))
        result = _sync(db_session, asset, _history(_session_bars(day, count=4)))

        assert result.inserted == 2
        assert result.skipped_existing == 2
        assert db_session.query(IntradayPrice).count() == 4

    def test_an_invalid_bar_is_rejected_rather_than_stored(self, db_session, asset):
        bad = IntradayBar(
            timestamp=_local(date(2026, 8, 18), 10, 15),
            timeframe=_15M,
            open=Decimal("42.00"),
            high=Decimal("41.00"),
            low=Decimal("40.00"),
            close=Decimal("42.50"),
            volume=Decimal(1000),
        )
        result = _sync(db_session, asset, _history([bad]))

        assert result.rejected == 1
        assert result.inserted == 0
        assert db_session.query(IntradayPrice).count() == 0

    def test_a_hole_is_reported_alongside_what_was_stored(self, db_session, asset):
        day = date(2026, 8, 18)
        bars = [_bar(_local(day, 10, 15)), _bar(_local(day, 11, 15))]
        result = _sync(db_session, asset, _history(bars))

        assert result.inserted == 2
        assert result.missing_bars == 3
        assert [coverage.session for coverage in result.sessions] == [day]


class TestTheWindowConflict:
    def _store_under_5d(self, db_session, asset, day: date):
        return _sync(
            db_session, asset, _history(_session_bars(day), HistoryWindow.FIVE_DAYS)
        )

    def test_a_session_stored_under_another_window_is_left_alone(
        self, db_session, asset
    ):
        day = date(2026, 8, 18)
        self._store_under_5d(db_session, asset, day)

        result = _sync(
            db_session,
            asset,
            # The 3mo partition carries a 10:00 bar the 5d one never has,
            # and disagrees about every shared label.
            _history(
                [_bar(_local(day, 10, 0), close="42.80")]
                + _session_bars(day, close="43.07"),
                HistoryWindow.THREE_MONTHS,
            ),
        )

        assert result.inserted == 0
        assert len(result.conflicts) == 1
        conflict = result.conflicts[0]
        assert conflict.session == day
        assert conflict.stored_window is HistoryWindow.FIVE_DAYS
        assert conflict.incoming_window is HistoryWindow.THREE_MONTHS
        assert conflict.bars_skipped == 5

    def test_the_stored_session_is_untouched_by_the_refusal(self, db_session, asset):
        day = date(2026, 8, 18)
        self._store_under_5d(db_session, asset, day)

        _sync(
            db_session,
            asset,
            _history(_session_bars(day, close="43.07"), HistoryWindow.THREE_MONTHS),
        )

        stored = db_session.query(IntradayPrice).all()
        assert len(stored) == 4
        assert {row.close for row in stored} == {Decimal("42.00")}
        assert {row.source_window for row in stored} == {"5d"}

    def test_other_sessions_in_the_same_batch_still_ingest(self, db_session, asset):
        """A conflict is about one session, not about the sync."""
        conflicted = date(2026, 8, 18)
        clean = date(2026, 8, 19)
        self._store_under_5d(db_session, asset, conflicted)

        result = _sync(
            db_session,
            asset,
            _history(
                _session_bars(conflicted, close="43.07")
                + _session_bars(clean, close="43.50"),
                HistoryWindow.THREE_MONTHS,
            ),
        )

        assert len(result.conflicts) == 1
        assert result.inserted == 4
        stored_clean = [
            row
            for row in db_session.query(IntradayPrice).all()
            if row.source_window == "3mo"
        ]
        assert len(stored_clean) == 4

    def test_resync_replaces_the_whole_session(self, db_session, asset):
        day = date(2026, 8, 18)
        self._store_under_5d(db_session, asset, day)

        result = _sync(
            db_session,
            asset,
            _history(
                [_bar(_local(day, 10, 0), close="42.80")]
                + _session_bars(day, close="43.07"),
                HistoryWindow.THREE_MONTHS,
            ),
            resync=True,
        )

        assert result.conflicts == []
        assert result.replaced == 4
        assert result.inserted == 5

        stored = db_session.query(IntradayPrice).all()
        assert len(stored) == 5
        assert {row.source_window for row in stored} == {"3mo"}
        assert Decimal("42.00") not in {row.close for row in stored}

    def test_the_same_window_is_never_a_conflict(self, db_session, asset):
        day = date(2026, 8, 18)
        self._store_under_5d(db_session, asset, day)
        result = self._store_under_5d(db_session, asset, day)
        assert result.conflicts == []


class TestReading:
    def test_stored_bars_come_back_ordered_and_aware(self, db_session, asset):
        day = date(2026, 8, 18)
        _sync(db_session, asset, _history(_session_bars(day)))

        bars = read_intraday_bars(db_session, asset, _15M, *_WINDOW)

        assert len(bars) == 4
        assert [bar.timestamp for bar in bars] == sorted(bar.timestamp for bar in bars)
        assert all(bar.timestamp.tzinfo is not None for bar in bars)

    def test_another_timeframe_is_not_returned(self, db_session, asset):
        _sync(db_session, asset, _history(_session_bars(date(2026, 8, 18))))
        assert (
            read_intraday_bars(db_session, asset, Timeframe.FIVE_MINUTES, *_WINDOW)
            == []
        )

    def test_reading_never_calls_the_provider(self, db_session, asset):
        """Rule 23, and it matters more here: the source serves intraday
        for only some tickers, so a read that reached out would fail for
        reasons unrelated to the read."""
        provider = FakeIntradayProvider(_history(_session_bars(date(2026, 8, 18))))
        sync_intraday_history(db_session, provider, asset, _15M, *_WINDOW)
        assert provider.calls == 1

        read_intraday_bars(db_session, asset, _15M, *_WINDOW)
        assert provider.calls == 1
