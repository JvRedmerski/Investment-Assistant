"""Tests for BrapiIndexProvider — no real network access.

The regression case runs the real `^BVSP` payload through the real
`BrapiProvider`, not through a stub, because the claim being checked is
precisely that an index needs no parser of its own: Brapi returns the
Ibovespa in the same shape it returns a stock. A stubbed
`MarketDataProvider` would assume that instead of demonstrating it.
"""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.domain.benchmarks.catalog import CDI, IBOVESPA
from app.domain.benchmarks.data_quality import validate_benchmark_series
from app.integrations.benchmarks.brapi_index import BrapiIndexProvider
from app.integrations.benchmarks.exceptions import (
    BenchmarkSeriesNotFoundError,
    BenchmarkUnavailableError,
    InvalidBenchmarkResponseError,
)
from app.integrations.benchmarks.schemas import BenchmarkKind, BenchmarkObservation
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.brapi import BrapiProvider
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)

# -- the live response ------------------------------------------------
#
# Verbatim bars from a real `GET /quote/^BVSP?range=1mo&interval=1d`
# captured on 2026-08-18. Note the last row: `volume` 0 and a fractional
# close, because it is the session **in progress**, not a close. Three
# requests minutes apart returned 166851.5156, then 166978.9375, then
# 166923.3438 for that same date — the value below is the second.

_REAL_IBOV_BARS = [
    # (epoch, open, high, low, close, volume, adjustedClose)
    (1784516400, 173714, 174311, 173222, 173371, 5028800, 173371),
    (1786590000, 167489, 168516, 166197, 167101, 10721100, 167101),
    (1786676400, 167100, 167100, 164835, 166934, 10883000, 166934),
    (1786935600, 166933, 168007, 166464, 166784, 9037400, 166784),
    (1787022000, 166788.875, 168389.4844, 166455.9844, 166978.9375, 0, 166978.9375),
]


def _real_payload():
    return {
        "results": [
            {
                "symbol": "^BVSP",
                "shortName": "IBOVESPA",
                "currency": "BRL",
                "regularMarketPrice": 166978.94,
                "regularMarketTime": "2026-08-18T17:26:44.000Z",
                "historicalDataPrice": [
                    {
                        "date": epoch,
                        "open": open_,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume,
                        "adjustedClose": adjusted,
                    }
                    for epoch, open_, high, low, close, volume, adjusted in (
                        _REAL_IBOV_BARS
                    )
                ],
            }
        ]
    }


def _live_provider(handler) -> BrapiIndexProvider:
    return BrapiIndexProvider(
        market_data=BrapiProvider(
            base_url="https://brapi.dev/api",
            token="test-token",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
    )


class _FakeMarketData(MarketDataProvider):
    """Raises whatever it was given, so error translation can be checked."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def get_quote(self, ticker):  # pragma: no cover - not used here
        raise self._error

    def get_daily_history(self, ticker, start, end):
        raise self._error


def test_regression_against_the_real_ibovespa_response():
    """The index parses through the stock code path, unchanged."""
    provider = _live_provider(lambda _: httpx.Response(200, json=_real_payload()))

    observations = provider.get_series(
        IBOVESPA.series_id, date(2026, 7, 20), date(2026, 8, 18), IBOVESPA.kind
    )

    assert [observation.date for observation in observations] == [
        date(2026, 7, 20),
        date(2026, 8, 13),
        date(2026, 8, 14),
        date(2026, 8, 17),
        date(2026, 8, 18),
    ]
    assert observations[0].value == Decimal(173371)
    assert observations[-1].value == Decimal("166978.9375")


def test_the_session_in_progress_is_fetched_but_never_stored():
    """The end-to-end guard against freezing an intraday level as a close.

    Brapi includes today's live bar in `historicalDataPrice` with an
    `adjustedClose` populated, so the ADR-016 `MISSING_ADJUSTED_CLOSE`
    check that protects stock bars does not fire here. `INCOMPLETE_PERIOD`
    is what stops it, and since ingestion never rewrites a stored date,
    it is the only thing standing between a moving number and a permanent
    record of it.
    """
    provider = _live_provider(lambda _: httpx.Response(200, json=_real_payload()))

    observations = provider.get_series(
        IBOVESPA.series_id, date(2026, 7, 20), date(2026, 8, 18), IBOVESPA.kind
    )
    report = validate_benchmark_series(observations, IBOVESPA, date(2026, 8, 18))

    assert len(report.valid_observations) == 4
    assert [issue.code for issue in report.errors] == ["INCOMPLETE_PERIOD"]
    assert report.errors[0].observation_date == date(2026, 8, 18)


def test_the_caret_in_the_ticker_reaches_the_provider_intact():
    """`^BVSP` is not a URL-safe path segment; a mangled one 404s."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=_real_payload())

    provider = _live_provider(handler)
    provider.get_series(
        IBOVESPA.series_id, date(2026, 8, 17), date(2026, 8, 17), IBOVESPA.kind
    )

    assert seen == ["/api/quote/^BVSP"]


def test_an_unadjusted_bar_is_passed_through_as_none_never_filled_in():
    """Held to the same contract as a stock bar (ADR-016)."""
    payload = {
        "results": [
            {
                "symbol": "^BVSP",
                "historicalDataPrice": [
                    {
                        "date": 1786935600,
                        "open": 166933,
                        "high": 168007,
                        "low": 166464,
                        "close": 166784,
                        "volume": 9037400,
                        "adjustedClose": None,
                    }
                ],
            }
        ]
    }
    provider = _live_provider(lambda _: httpx.Response(200, json=payload))

    observations = provider.get_series(
        IBOVESPA.series_id, date(2026, 8, 17), date(2026, 8, 17), IBOVESPA.kind
    )

    assert observations == [BenchmarkObservation(date=date(2026, 8, 17), value=None)]


def test_a_rate_kind_is_refused_because_this_source_publishes_levels():
    provider = BrapiIndexProvider(market_data=_FakeMarketData(RuntimeError()))

    with pytest.raises(ValueError):
        provider.get_series("^BVSP", date(2026, 8, 1), date(2026, 8, 17), CDI.kind)


def test_start_after_end_is_rejected():
    provider = BrapiIndexProvider(market_data=_FakeMarketData(RuntimeError()))

    with pytest.raises(ValueError):
        provider.get_series(
            "^BVSP", date(2026, 8, 17), date(2026, 8, 1), BenchmarkKind.INDEX
        )


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (TickerNotFoundError("gone"), BenchmarkSeriesNotFoundError),
        (MarketDataUnavailableError("down"), BenchmarkUnavailableError),
        (InvalidMarketDataResponseError("garbage"), InvalidBenchmarkResponseError),
    ],
)
def test_market_data_errors_are_retold_in_the_benchmark_vocabulary(raised, expected):
    """A caller of the benchmark package never sees a market data error.

    That is what lets a benchmark's backing source change without any
    caller learning about it.
    """
    provider = BrapiIndexProvider(market_data=_FakeMarketData(raised))

    with pytest.raises(expected):
        provider.get_series(
            "^BVSP", date(2026, 8, 1), date(2026, 8, 17), BenchmarkKind.INDEX
        )
