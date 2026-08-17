"""Tests for BrapiProvider using httpx.MockTransport — no real network
access, no extra mocking dependency (httpx already ships MockTransport).
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from app.integrations.market_data.brapi import BrapiProvider
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


def test_get_daily_history_defaults_adjusted_close_to_close_when_absent():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _history_payload()
        del payload["results"][0]["historicalDataPrice"][0]["adjustedClose"]
        return httpx.Response(200, json=payload)

    provider = _provider(handler)
    bars = provider.get_daily_history("PETR4", date(2026, 1, 2), date(2026, 1, 2))

    assert bars[0].adjusted_close == bars[0].close


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
    with patch("app.integrations.market_data.brapi.time.sleep"):
        quote = provider.get_quote("PETR4")

    assert calls["count"] == 2
    assert quote.price == Decimal("38.5")


def test_raises_market_data_unavailable_after_exhausting_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    provider = _provider(handler, max_retries=3)
    with (
        patch("app.integrations.market_data.brapi.time.sleep"),
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
    with patch("app.integrations.market_data.brapi.time.sleep"):
        quote = provider.get_quote("PETR4")

    assert calls["count"] == 2
    assert quote.price == Decimal("38.5")


def test_min_request_interval_throttles_consecutive_requests():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_quote_payload())

    provider = _provider(handler, min_request_interval=2.0)

    with (
        patch("app.integrations.market_data.brapi.time.sleep") as mock_sleep,
        patch(
            "app.integrations.market_data.brapi.time.monotonic",
            side_effect=[100.0, 100.5, 100.5],
        ),
    ):
        provider.get_quote("PETR4")
        provider.get_quote("PETR4")

    mock_sleep.assert_called_once()
    (slept_for,) = mock_sleep.call_args.args
    assert slept_for == pytest.approx(1.5)
