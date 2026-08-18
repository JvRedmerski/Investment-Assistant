"""Tests for BrapiProvider using httpx.MockTransport — no real network
access, no extra mocking dependency (httpx already ships MockTransport).
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from app.integrations.market_data.brapi import BrapiProvider
from app.integrations.market_data.data_quality import validate_daily_bars
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)


def _epoch(year, month, day) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp())


def _quote_payload(price=38.5, currency="BRL", as_of="2026-01-10T18:00:00+00:00"):
    return {
        "results": [
            {
                "symbol": "PETR4",
                "regularMarketPrice": price,
                "currency": currency,
                "regularMarketTime": as_of,
            }
        ]
    }


def _history_payload():
    return {
        "results": [
            {
                "symbol": "PETR4",
                "historicalDataPrice": [
                    {
                        "date": _epoch(2026, 1, 2),
                        "open": 38.0,
                        "high": 39.0,
                        "low": 37.5,
                        "close": 38.5,
                        "adjustedClose": 38.5,
                        "volume": 1_000_000,
                    },
                    {
                        "date": _epoch(2026, 1, 3),
                        "open": 38.5,
                        "high": 39.5,
                        "low": 38.0,
                        "close": 39.0,
                        "adjustedClose": 39.0,
                        "volume": 1_200_000,
                    },
                ],
            }
        ]
    }


def _provider(handler, **kwargs) -> BrapiProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return BrapiProvider(
        client=client, max_retries=kwargs.pop("max_retries", 1), **kwargs
    )


def test_get_quote_parses_a_successful_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/quote/PETR4"
        return httpx.Response(200, json=_quote_payload())

    provider = _provider(handler)
    quote = provider.get_quote("PETR4")

    assert quote.ticker == "PETR4"
    assert quote.price == Decimal("38.5")
    assert quote.currency == "BRL"
    assert quote.as_of == datetime(2026, 1, 10, 18, 0, tzinfo=UTC)


def test_get_quote_raises_ticker_not_found_on_http_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    provider = _provider(handler)
    with pytest.raises(TickerNotFoundError):
        provider.get_quote("NONEXISTENT")


def test_get_quote_raises_ticker_not_found_on_empty_results():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    provider = _provider(handler)
    with pytest.raises(TickerNotFoundError):
        provider.get_quote("PETR4")


def test_get_quote_raises_on_missing_required_field():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _quote_payload()
        del payload["results"][0]["regularMarketPrice"]
        return httpx.Response(200, json=payload)

    provider = _provider(handler)
    with pytest.raises(InvalidMarketDataResponseError):
        provider.get_quote("PETR4")


def test_get_quote_raises_on_null_price():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_quote_payload(price=None))

    provider = _provider(handler)
    with pytest.raises(InvalidMarketDataResponseError):
        provider.get_quote("PETR4")


def test_get_quote_raises_on_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    provider = _provider(handler)
    with pytest.raises(InvalidMarketDataResponseError):
        provider.get_quote("PETR4")


def test_get_daily_history_parses_and_filters_by_date():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["interval"] == "1d"
        return httpx.Response(200, json=_history_payload())

    provider = _provider(handler)
    bars = provider.get_daily_history("PETR4", date(2026, 1, 2), date(2026, 1, 2))

    assert len(bars) == 1
    bar = bars[0]
    assert bar.date == date(2026, 1, 2)
    assert bar.open == Decimal("38.0")
    assert bar.high == Decimal("39.0")
    assert bar.low == Decimal("37.5")
    assert bar.close == Decimal("38.5")
    assert bar.adjusted_close == Decimal("38.5")
    assert bar.volume == Decimal(1000000)


def test_absent_adjusted_close_is_reported_as_none_never_defaulted_to_close():
    """The adjusted close is not fabricated from the raw close.

    They are different quantities — the adjusted close nets out dividends
    and splits — so substituting one for the other invents an adjustment
    that does not exist (rule 44 / ADR-014). The bar is later rejected by
    `validate_daily_bars`, so the fabrication would not merely be wrong,
    it would be frozen forever: `sync_daily_history` never rewrites a
    stored date.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        payload = _history_payload()
        del payload["results"][0]["historicalDataPrice"][0]["adjustedClose"]
        return httpx.Response(200, json=payload)

    provider = _provider(handler)
    bars = provider.get_daily_history("PETR4", date(2026, 1, 2), date(2026, 1, 2))

    assert bars[0].adjusted_close is None
    assert bars[0].close == Decimal("38.5")


def test_explicit_null_adjusted_close_is_also_reported_as_none():
    # The live API sends an explicit `null`, not an absent key.
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _history_payload()
        payload["results"][0]["historicalDataPrice"][0]["adjustedClose"] = None
        return httpx.Response(200, json=payload)

    provider = _provider(handler)
    bars = provider.get_daily_history("PETR4", date(2026, 1, 2), date(2026, 1, 2))

    assert bars[0].adjusted_close is None


def test_get_daily_history_raises_when_history_field_is_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"symbol": "PETR4"}]})

    provider = _provider(handler)
    with pytest.raises(InvalidMarketDataResponseError):
        provider.get_daily_history("PETR4", date(2026, 1, 1), date(2026, 1, 31))


def test_get_daily_history_rejects_start_after_end():
    provider = _provider(lambda request: httpx.Response(200, json=_history_payload()))
    with pytest.raises(ValueError):
        provider.get_daily_history("PETR4", date(2026, 1, 31), date(2026, 1, 1))


def test_retries_on_transient_server_error_then_succeeds():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, text="service unavailable")
        return httpx.Response(200, json=_quote_payload())

    provider = _provider(handler, max_retries=3)
    with patch("app.integrations.http.time.sleep"):
        quote = provider.get_quote("PETR4")

    assert calls["count"] == 2
    assert quote.price == Decimal("38.5")


def test_raises_market_data_unavailable_after_exhausting_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    provider = _provider(handler, max_retries=3)
    with (
        patch("app.integrations.http.time.sleep"),
        pytest.raises(MarketDataUnavailableError),
    ):
        provider.get_quote("PETR4")


def test_non_retryable_http_error_fails_immediately_without_retrying():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400, text="bad request")

    provider = _provider(handler, max_retries=3)
    with pytest.raises(MarketDataUnavailableError):
        provider.get_quote("PETR4")

    assert calls["count"] == 1


def test_retries_on_timeout_then_succeeds():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(200, json=_quote_payload())

    provider = _provider(handler, max_retries=3)
    with patch("app.integrations.http.time.sleep"):
        quote = provider.get_quote("PETR4")

    assert calls["count"] == 2
    assert quote.price == Decimal("38.5")


def test_min_request_interval_throttles_consecutive_requests():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_quote_payload())

    provider = _provider(handler, min_request_interval=2.0)

    with (
        patch("app.integrations.http.time.sleep") as mock_sleep,
        patch(
            "app.integrations.http.time.monotonic",
            side_effect=[100.0, 100.5, 100.5],
        ),
    ):
        provider.get_quote("PETR4")
        provider.get_quote("PETR4")

    mock_sleep.assert_called_once()
    (slept_for,) = mock_sleep.call_args.args
    assert slept_for == pytest.approx(1.5)


# -- regression against live responses, one per asset type -----------
#
# W06-003 validated the mapping against PETR4 (a common stock) only,
# leaving open whether other B3 asset classes come back in a different
# shape. These three payloads are verbatim rows from live
# `GET /quote/{ticker}?range=1mo&interval=1d` responses captured on
# 2026-08-18 — one FII, one ETF and one bank. All three parse through
# the same mapping as PETR4, so the shape is asset-class agnostic.
#
# Each also pins the real-world null `adjustedClose`: the source leaves
# the most recently closed session unadjusted for a while (2026-08-17 in
# all three), filling it in later.

_LIVE_RESPONSES = {
    # (FII) Patria Log FII
    "HGLG11": {
        "market_price": 144.15,
        "market_time": "2026-08-18T16:02:30.000Z",
        "bars": [
            (1784516400, 149.14, 149.29, 148.45, 148.5, 104317, 147.3214),
            (1786935600, 146.29, 146.78, 143.39, 145.11, 167550, None),
            (1787022000, 145.11, 145.22, 143.51, 144.15, 69232, 144.15),
        ],
    },
    # (ETF) iShares Ibovespa
    "BOVA11": {
        "market_price": 163.98,
        "market_time": "2026-08-18T16:02:30.000Z",
        "bars": [
            (1784516400, 170.7, 171.4, 170.16, 170.3, 2648578, 170.3),
            (1786935600, 164.11, 165.19, 163.64, 163.8, 2971451, None),
            (1787022000, 164.05, 165.62, 163.9, 163.98, 636506, 163.98),
        ],
    },
    # (bank) Itau Unibanco PN
    "ITUB4": {
        "market_price": 38.48,
        "market_time": "2026-08-18T16:04:30.000Z",
        "bars": [
            (1784516400, 42.14, 42.53, 42.1, 42.3, 12612200, 42.2821),
            (1786935600, 38.92, 38.98, 38.17, 38.38, 21823400, None),
            (1787022000, 38.48, 38.74, 38.26, 38.48, 5440800, 38.48),
        ],
    },
}


#: `regularMarketTime` comes back as an ISO-8601 string with a trailing
#: Z, unlike the epoch integers used inside `historicalDataPrice`.
_EXPECTED_QUOTE_TIME = {
    "HGLG11": datetime(2026, 8, 18, 16, 2, 30, tzinfo=UTC),
    "BOVA11": datetime(2026, 8, 18, 16, 2, 30, tzinfo=UTC),
    "ITUB4": datetime(2026, 8, 18, 16, 4, 30, tzinfo=UTC),
}


def _live_payload(ticker):
    live = _LIVE_RESPONSES[ticker]
    return {
        "results": [
            {
                "symbol": ticker,
                "currency": "BRL",
                "regularMarketPrice": live["market_price"],
                "regularMarketTime": live["market_time"],
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
                    for epoch, open_, high, low, close, volume, adjusted in live["bars"]
                ],
            }
        ]
    }


@pytest.mark.parametrize("ticker", sorted(_LIVE_RESPONSES))
def test_regression_against_real_responses_per_asset_type(ticker):
    """FIIs, ETFs and banks use the same response shape as a stock."""
    provider = _provider(
        lambda request: httpx.Response(200, json=_live_payload(ticker))
    )

    bars = provider.get_daily_history(ticker, date(2026, 7, 20), date(2026, 8, 18))

    assert [bar.date for bar in bars] == [
        date(2026, 7, 20),
        date(2026, 8, 17),
        date(2026, 8, 18),
    ]
    expected = _LIVE_RESPONSES[ticker]["bars"]
    for bar, (_, open_, high, low, close, volume, adjusted) in zip(bars, expected):
        assert bar.open == Decimal(str(open_))
        assert bar.high == Decimal(str(high))
        assert bar.low == Decimal(str(low))
        assert bar.close == Decimal(str(close))
        assert bar.volume == Decimal(str(volume))
        assert bar.adjusted_close == (
            Decimal(str(adjusted)) if adjusted is not None else None
        )

    # 2026-08-17 came back unadjusted from the live API in all three
    # tickers: preserved as None here, and dropped before storage.
    unadjusted = next(bar for bar in bars if bar.date == date(2026, 8, 17))
    assert unadjusted.adjusted_close is None

    report = validate_daily_bars(bars)

    assert [bar.date for bar in report.valid_bars] == [
        date(2026, 7, 20),
        date(2026, 8, 18),
    ]
    assert [issue.code for issue in report.errors] == ["MISSING_ADJUSTED_CLOSE"]


@pytest.mark.parametrize("ticker", sorted(_LIVE_RESPONSES))
def test_get_quote_parses_real_responses_per_asset_type(ticker):
    provider = _provider(
        lambda request: httpx.Response(200, json=_live_payload(ticker))
    )

    quote = provider.get_quote(ticker)

    assert quote.ticker == ticker
    assert quote.price == Decimal(str(_LIVE_RESPONSES[ticker]["market_price"]))
    assert quote.currency == "BRL"
    assert quote.as_of == _EXPECTED_QUOTE_TIME[ticker]
