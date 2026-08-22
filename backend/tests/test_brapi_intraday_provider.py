"""Brapi's intraday path (W15-002), using httpx.MockTransport - no network.

Every fixture below is a **captured** live response, not one written from
the documentation. The distinction is the whole lesson of W06-003: a mock
built on an assumption does not verify the assumption, it reproduces it.
The capture was taken on 2026-08-22 and each number that appears here was
printed by the real API.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.integrations.market_data.brapi import (
    BrapiProvider,
    _intraday_window_for,
)
from app.integrations.market_data.exceptions import (
    HistoryWindowTooLargeError,
    IntradayNotAvailableError,
    InvalidMarketDataResponseError,
)
from app.integrations.market_data.schemas import HistoryWindow, Timeframe

# --- captured from the live response -----------------------------------
#
# PETR4, 15-minute bars, `range=5d`, session of 2026-08-18. Epochs and
# OHLCV verbatim; `adjustedClose` was null on this bar and on all 1,388
# others in the capture.
_REAL_5D_BARS = [
    {
        "date": 1787058900,  # 2026-08-18 13:15 UTC = 10:15 local
        "open": 42.91,
        "high": 42.96,
        "low": 42.86,
        "close": 42.89,
        "volume": 1161600,
        "adjustedClose": None,
    },
    {
        "date": 1787063400,  # 2026-08-18 14:30 UTC = 11:30 local
        "open": 43.06,
        "high": 43.06,
        "low": 42.88,
        "close": 42.90,
        "volume": 955400,
        "adjustedClose": None,
    },
]

# The same ticker, same timeframe, same session, asked as `range=3mo`.
# A different partition of the same trading day: it carries a 10:00 bar
# the short windows never return, and the 10:15 bar disagrees with the
# one above. See ADR-036.
_REAL_3MO_BARS = [
    {
        "date": 1787058000,  # 2026-08-18 13:00 UTC = 10:00 local
        "open": 42.80,
        "high": 43.00,
        "low": 42.80,
        "close": 42.92,
        "volume": 1012700,
        "adjustedClose": None,
    },
    {
        "date": 1787058900,  # the same 10:15 label as above
        "open": 42.92,
        "high": 43.10,
        "low": 42.85,
        "close": 43.07,
        "volume": 1186700,
        "adjustedClose": None,
    },
]

# Verbatim body of the refusal, captured from BBAS3 at `interval=15m`.
# The message blames the interval; the measurement says otherwise (see
# `IntradayNotAvailableError`).
_REAL_REFUSAL = {
    "error": True,
    "message": (
        'O intervalo "15m" nao esta disponivel no seu plano. '
        "Intervalos permitidos: 1d."
    ),
    "code": "INVALID_INTERVAL",
    "details": {"feature": "__historical_interval__"},
}


def _provider(handler) -> BrapiProvider:
    return BrapiProvider(
        base_url="https://brapi.dev/api",
        token="test-token",
        max_retries=1,
        min_request_interval=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _ok(bars, *, used_interval="15m"):
    def handler(request: httpx.Request) -> httpx.Response:
        handler.request = request
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "symbol": "PETR4",
                        "usedInterval": used_interval,
                        "usedRange": request.url.params.get("range"),
                        "historicalDataPrice": bars,
                    }
                ]
            },
        )

    return handler


_WINDOW = (
    datetime(2026, 8, 18, tzinfo=UTC),
    datetime(2026, 8, 19, tzinfo=UTC),
)


class TestParsingTheRealResponse:
    def test_regression_against_the_real_petr4_intraday_response(self):
        """Locks in the field mapping verified live on 2026-08-22.

        If Brapi renames `historicalDataPrice`, changes `date` away from
        epoch seconds, or starts nesting the OHLCV differently, this
        fails loudly instead of silently storing nothing - which is
        exactly how the pre-verification fundamentals mapping slipped
        through.
        """
        provider = _provider(_ok(_REAL_5D_BARS))
        history = provider.get_intraday_history(
            "PETR4", Timeframe.FIFTEEN_MINUTES, *_WINDOW
        )

        assert history.timeframe is Timeframe.FIFTEEN_MINUTES
        assert len(history.bars) == 2

        first = history.bars[0]
        assert first.timestamp == datetime(2026, 8, 18, 13, 15, tzinfo=UTC)
        assert first.open == Decimal("42.91")
        assert first.high == Decimal("42.96")
        assert first.low == Decimal("42.86")
        assert first.close == Decimal("42.89")
        assert first.volume == Decimal(1161600)

    def test_epoch_seconds_become_utc_instants(self):
        provider = _provider(_ok(_REAL_5D_BARS))
        history = provider.get_intraday_history(
            "PETR4", Timeframe.FIFTEEN_MINUTES, *_WINDOW
        )
        assert all(bar.timestamp.tzinfo is not None for bar in history.bars)
        assert history.bars[1].timestamp == datetime(2026, 8, 18, 14, 30, tzinfo=UTC)

    def test_the_null_adjusted_close_is_not_carried_anywhere(self):
        """It is null on every intraday row the API returns. Nothing
        reads it, and nothing fills it from `close` (ADR-023)."""
        provider = _provider(_ok(_REAL_5D_BARS))
        history = provider.get_intraday_history(
            "PETR4", Timeframe.FIFTEEN_MINUTES, *_WINDOW
        )
        assert not hasattr(history.bars[0], "adjusted_close")

    def test_bars_outside_the_requested_window_are_dropped(self):
        provider = _provider(_ok(_REAL_5D_BARS))
        history = provider.get_intraday_history(
            "PETR4",
            Timeframe.FIFTEEN_MINUTES,
            datetime(2026, 8, 18, 14, 0, tzinfo=UTC),
            datetime(2026, 8, 18, 15, 0, tzinfo=UTC),
        )
        assert [bar.timestamp.hour for bar in history.bars] == [14]

    def test_a_missing_field_is_named_rather_than_defaulted(self):
        broken = [{"date": 1787058900, "open": 42.91, "high": 42.96}]
        provider = _provider(_ok(broken))
        with pytest.raises(InvalidMarketDataResponseError, match="low, close, volume"):
            provider.get_intraday_history("PETR4", Timeframe.FIFTEEN_MINUTES, *_WINDOW)


class TestTheWindowTravelsWithTheBars:
    def test_the_window_actually_requested_is_reported_back(self):
        handler = _ok(_REAL_5D_BARS)
        provider = _provider(handler)
        history = provider.get_intraday_history(
            "PETR4",
            Timeframe.FIFTEEN_MINUTES,
            datetime.now(UTC) - timedelta(days=3),
            datetime.now(UTC),
        )
        assert history.window is HistoryWindow.FIVE_DAYS
        assert handler.request.url.params.get("range") == "5d"
        assert handler.request.url.params.get("interval") == "15m"

    def test_two_windows_disagree_about_the_same_session(self):
        """The measured fact behind ADR-036, reproduced from the capture.

        Same ticker, same timeframe, same 10:15 label - different bar.
        Nothing in this project may merge these two series.
        """
        short = _provider(_ok(_REAL_5D_BARS)).get_intraday_history(
            "PETR4", Timeframe.FIFTEEN_MINUTES, *_WINDOW
        )
        long = _provider(_ok(_REAL_3MO_BARS)).get_intraday_history(
            "PETR4", Timeframe.FIFTEEN_MINUTES, *_WINDOW
        )

        at_1015 = datetime(2026, 8, 18, 13, 15, tzinfo=UTC)
        short_bar = next(b for b in short.bars if b.timestamp == at_1015)
        long_bar = next(b for b in long.bars if b.timestamp == at_1015)

        assert short_bar.close != long_bar.close
        assert short_bar.volume != long_bar.volume
        # And the long window carries an opening bar the short one never has.
        assert min(b.timestamp for b in long.bars) < min(
            b.timestamp for b in short.bars
        )


class TestTheWindowTable:
    @pytest.mark.parametrize(
        ("timeframe", "days_back", "expected"),
        [
            (Timeframe.ONE_MINUTE, 0, HistoryWindow.ONE_DAY),
            (Timeframe.ONE_MINUTE, 3, HistoryWindow.FIVE_DAYS),
            (Timeframe.ONE_MINUTE, 20, HistoryWindow.ONE_MONTH),
            (Timeframe.FIVE_MINUTES, 60, HistoryWindow.THREE_MONTHS),
            (Timeframe.FIFTEEN_MINUTES, 60, HistoryWindow.THREE_MONTHS),
        ],
    )
    def test_the_smallest_window_that_reaches_start(
        self, timeframe, days_back, expected
    ):
        today = date(2026, 8, 22)
        assert (
            _intraday_window_for(timeframe, today - timedelta(days=days_back), today)
            is expected
        )

    def test_one_minute_never_escalates_to_three_months(self):
        """Measured: `1m` at `range=3mo` returns five sessions where
        `1mo` returns twenty-two, while still echoing `usedRange: 3mo`.
        Escalating there would silently serve *less* history the further
        back the caller asked."""
        today = date(2026, 8, 22)
        with pytest.raises(HistoryWindowTooLargeError, match="1m"):
            _intraday_window_for(
                Timeframe.ONE_MINUTE, today - timedelta(days=60), today
            )

    def test_the_bucket_is_chosen_from_today_not_from_the_window_length(self):
        """Every Brapi range is anchored at today and the API takes no
        start date, so a two-day window three weeks back still needs the
        bucket that reaches three weeks."""
        today = date(2026, 8, 22)
        assert (
            _intraday_window_for(
                Timeframe.FIFTEEN_MINUTES, today - timedelta(days=21), today
            )
            is HistoryWindow.ONE_MONTH
        )


class TestTheRefusalIsNotAnOutage:
    def test_invalid_interval_becomes_its_own_error(self):
        """Captured verbatim from BBAS3. Mapped by status alone this
        would read as `MarketDataUnavailableError` - "could not be
        reached" - and invite a retry that can never succeed."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json=_REAL_REFUSAL)

        provider = _provider(handler)
        with pytest.raises(IntradayNotAvailableError, match="intraday bars"):
            provider.get_intraday_history("BBAS3", Timeframe.FIFTEEN_MINUTES, *_WINDOW)

    def test_a_plain_400_still_maps_the_way_it_always_did(self):
        """The hook names one error; it does not take over the others."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": True, "code": "SOMETHING_ELSE"})

        provider = _provider(handler)
        with pytest.raises(Exception) as caught:
            provider.get_intraday_history("PETR4", Timeframe.FIFTEEN_MINUTES, *_WINDOW)
        assert not isinstance(caught.value, IntradayNotAvailableError)


class TestRule47:
    def test_a_downgraded_interval_is_refused_not_stored(self):
        """Storing a daily bar in `intraday_prices` is precisely what
        rule 47 forbids, and nothing downstream could detect it."""
        provider = _provider(_ok(_REAL_5D_BARS, used_interval="1d"))
        with pytest.raises(InvalidMarketDataResponseError, match="rule 47"):
            provider.get_intraday_history("PETR4", Timeframe.FIFTEEN_MINUTES, *_WINDOW)

    def test_a_naive_window_is_refused(self):
        provider = _provider(_ok(_REAL_5D_BARS))
        with pytest.raises(ValueError, match="timezone-aware"):
            provider.get_intraday_history(
                "PETR4",
                Timeframe.FIFTEEN_MINUTES,
                datetime(2026, 8, 18),  # noqa: DTZ001
                datetime(2026, 8, 19),  # noqa: DTZ001
            )
