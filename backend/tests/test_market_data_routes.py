"""Integration tests for the price sync/read endpoints, overriding
get_market_data_provider with a fake so nothing hits the network."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.dependencies import get_market_data_provider
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.exceptions import (
    HistoryWindowTooLargeError,
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import DailyBar, Quote
from app.main import app

ASSETS_URL = "/api/v1/assets"


class FakeProvider(MarketDataProvider):
    def __init__(self, bars=None, error=None, quote=None):
        self._bars = bars or []
        self._error = error
        self._quote = quote

    def get_quote(self, ticker):
        if self._error is not None:
            raise self._error
        return self._quote

    def get_daily_history(self, ticker, start, end):
        if self._error is not None:
            raise self._error
        return [bar for bar in self._bars if start <= bar.date <= end]


def _quote(ticker: str) -> Quote:
    return Quote(
        ticker=ticker,
        price=Decimal("61.42"),
        currency="BRL",
        as_of=datetime(2026, 8, 19, 18, 0, tzinfo=UTC),
    )


def _bar(day: int) -> DailyBar:
    return DailyBar(
        date=date(2026, 1, day),
        open=Decimal("38.0"),
        high=Decimal("39.0"),
        low=Decimal("37.5"),
        close=Decimal("38.5"),
        adjusted_close=Decimal("38.5"),
        volume=Decimal(1_000_000),
    )


@pytest.fixture(autouse=True)
def _reset_provider_override():
    yield
    app.dependency_overrides.pop(get_market_data_provider, None)


def _override_provider(provider: FakeProvider) -> None:
    app.dependency_overrides[get_market_data_provider] = lambda: provider


def _auth_headers(client, email="md-owner@example.com", password="SuperSecret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_asset(client, headers, ticker="PETR4"):
    response = client.post(
        ASSETS_URL,
        json={"ticker": ticker, "name": "Petrobras PN", "asset_type": "STOCK"},
        headers=headers,
    )
    return response.json()


def test_sync_requires_authentication(client):
    response = client.post(f"{ASSETS_URL}/PETR4/prices/sync", json={})
    assert response.status_code == 401


def test_sync_returns_not_found_for_unregistered_asset(client):
    headers = _auth_headers(client)
    _override_provider(FakeProvider(bars=[_bar(2)]))

    response = client.post(
        f"{ASSETS_URL}/NONEXISTENT/prices/sync", json={}, headers=headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_sync_inserts_bars_and_read_endpoint_returns_them_without_new_calls(client):
    headers = _auth_headers(client, email="md-owner-a@example.com")
    _create_asset(client, headers, ticker="VALE3")
    _override_provider(FakeProvider(bars=[_bar(2), _bar(3)]))

    sync_response = client.post(
        f"{ASSETS_URL}/VALE3/prices/sync",
        json={"start": "2026-01-01", "end": "2026-01-05"},
        headers=headers,
    )
    assert sync_response.status_code == 200
    data = sync_response.json()
    assert data["fetched"] == 2
    assert data["inserted"] == 2
    assert data["skipped_existing"] == 0

    # Swap in a provider that would error if called, to prove the read
    # endpoint never touches it (AGENTS.md rule 23 - cache, don't refetch).
    class ExplodingProvider(MarketDataProvider):
        def get_quote(self, ticker):
            raise AssertionError("must not be called")

        def get_daily_history(self, ticker, start, end):
            raise AssertionError("must not be called")

    _override_provider(ExplodingProvider())

    read_response = client.get(f"{ASSETS_URL}/VALE3/prices", headers=headers)
    assert read_response.status_code == 200
    prices = read_response.json()
    assert len(prices) == 2
    assert prices[0]["date"] == "2026-01-02"
    assert prices[1]["date"] == "2026-01-03"


def test_sync_is_idempotent_across_repeated_calls(client):
    headers = _auth_headers(client, email="md-owner-b@example.com")
    _create_asset(client, headers, ticker="ITUB4")
    _override_provider(FakeProvider(bars=[_bar(2), _bar(3)]))

    first = client.post(
        f"{ASSETS_URL}/ITUB4/prices/sync",
        json={"start": "2026-01-01", "end": "2026-01-05"},
        headers=headers,
    )
    second = client.post(
        f"{ASSETS_URL}/ITUB4/prices/sync",
        json={"start": "2026-01-01", "end": "2026-01-05"},
        headers=headers,
    )

    assert first.json()["inserted"] == 2
    assert second.json()["inserted"] == 0
    assert second.json()["skipped_existing"] == 2


def test_sync_maps_ticker_not_found_provider_error(client):
    headers = _auth_headers(client, email="md-owner-c@example.com")
    _create_asset(client, headers, ticker="BBAS3")
    _override_provider(FakeProvider(error=TickerNotFoundError("BBAS3")))

    response = client.post(f"{ASSETS_URL}/BBAS3/prices/sync", json={}, headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MARKET_DATA_TICKER_NOT_FOUND"


def test_sync_maps_unavailable_provider_error(client):
    headers = _auth_headers(client, email="md-owner-d@example.com")
    _create_asset(client, headers, ticker="WEGE3")
    _override_provider(FakeProvider(error=MarketDataUnavailableError("down")))

    response = client.post(f"{ASSETS_URL}/WEGE3/prices/sync", json={}, headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MARKET_DATA_UNAVAILABLE"


def test_sync_maps_invalid_response_provider_error(client):
    headers = _auth_headers(client, email="md-owner-e@example.com")
    _create_asset(client, headers, ticker="MGLU3")
    _override_provider(
        FakeProvider(error=InvalidMarketDataResponseError("bad payload"))
    )

    response = client.post(f"{ASSETS_URL}/MGLU3/prices/sync", json={}, headers=headers)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MARKET_DATA_INVALID_RESPONSE"


def test_read_prices_requires_authentication(client):
    response = client.get(f"{ASSETS_URL}/PETR4/prices")
    assert response.status_code == 401


def test_read_prices_filters_by_date_range(client):
    headers = _auth_headers(client, email="md-owner-f@example.com")
    _create_asset(client, headers, ticker="RENT3")
    _override_provider(FakeProvider(bars=[_bar(2), _bar(3), _bar(4)]))

    client.post(
        f"{ASSETS_URL}/RENT3/prices/sync",
        json={"start": "2026-01-01", "end": "2026-01-10"},
        headers=headers,
    )

    response = client.get(
        f"{ASSETS_URL}/RENT3/prices?start=2026-01-03&end=2026-01-03", headers=headers
    )
    assert response.status_code == 200
    prices = response.json()
    assert len(prices) == 1
    assert prices[0]["date"] == "2026-01-03"


# --- request window validation --------------------------------------


def test_sync_rejects_an_end_date_in_the_future(client):
    """`PriceSyncRequest` documented this and never enforced it.

    A future `end` is not a window any provider can answer: the response
    would carry whatever exists today while the reported range claimed
    sessions that have not happened.
    """
    headers = _auth_headers(client, email="md-owner-future@example.com")
    _create_asset(client, headers, ticker="BBAS3")
    _override_provider(FakeProvider(bars=[]))

    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    response = client.post(
        f"{ASSETS_URL}/BBAS3/prices/sync",
        json={"end": tomorrow.isoformat()},
        headers=headers,
    )

    assert response.status_code == 422


def test_sync_accepts_today_as_end_date(client):
    """The boundary is inclusive - today is not the future."""
    headers = _auth_headers(client, email="md-owner-today@example.com")
    _create_asset(client, headers, ticker="ITSA4")
    _override_provider(FakeProvider(bars=[]))

    today = datetime.now(UTC).date()
    response = client.post(
        f"{ASSETS_URL}/ITSA4/prices/sync",
        json={"end": today.isoformat()},
        headers=headers,
    )

    assert response.status_code == 200


def test_sync_maps_window_too_large_to_a_client_error(client):
    """400, not 502: it is the request that has to change.

    The provider plan caps how far back a range reaches, and the message
    has to say so - the old behaviour was an opaque upstream HTTP 400
    surfacing as a generic provider failure.
    """
    headers = _auth_headers(client, email="md-owner-window@example.com")
    _create_asset(client, headers, ticker="SUZB3")
    _override_provider(
        FakeProvider(error=HistoryWindowTooLargeError("needs 365 days of range"))
    )

    response = client.post(f"{ASSETS_URL}/SUZB3/prices/sync", json={}, headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MARKET_DATA_WINDOW_TOO_LARGE"
    assert "365 days" in response.json()["error"]["message"]


# --- quote endpoint --------------------------------------------------


def test_quote_requires_authentication(client):
    response = client.get(f"{ASSETS_URL}/PETR4/quote")
    assert response.status_code == 401


def test_quote_returns_the_providers_latest_price(client):
    headers = _auth_headers(client, email="md-owner-quote@example.com")
    _create_asset(client, headers, ticker="VALE3")
    _override_provider(FakeProvider(quote=_quote("VALE3")))

    response = client.get(f"{ASSETS_URL}/VALE3/quote", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "VALE3"
    assert Decimal(body["price"]) == Decimal("61.42")
    assert body["currency"] == "BRL"


def test_quote_requires_the_asset_to_be_registered(client):
    """A typo must not spend a request against a monthly quota."""
    headers = _auth_headers(client, email="md-owner-quote-b@example.com")
    _override_provider(FakeProvider(quote=_quote("PETR4")))

    response = client.get(f"{ASSETS_URL}/NOPE11/quote", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_quote_maps_ticker_not_found_at_the_provider(client):
    headers = _auth_headers(client, email="md-owner-quote-c@example.com")
    _create_asset(client, headers, ticker="EGIE3")
    _override_provider(FakeProvider(error=TickerNotFoundError("unknown")))

    response = client.get(f"{ASSETS_URL}/EGIE3/quote", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MARKET_DATA_TICKER_NOT_FOUND"


def test_quote_maps_provider_unavailable(client):
    headers = _auth_headers(client, email="md-owner-quote-d@example.com")
    _create_asset(client, headers, ticker="TAEE11")
    _override_provider(FakeProvider(error=MarketDataUnavailableError("down")))

    response = client.get(f"{ASSETS_URL}/TAEE11/quote", headers=headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MARKET_DATA_UNAVAILABLE"


def test_quote_maps_unparseable_provider_response(client):
    headers = _auth_headers(client, email="md-owner-quote-e@example.com")
    _create_asset(client, headers, ticker="KLBN11")
    _override_provider(FakeProvider(error=InvalidMarketDataResponseError("bad")))

    response = client.get(f"{ASSETS_URL}/KLBN11/quote", headers=headers)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MARKET_DATA_INVALID_RESPONSE"


def test_quote_is_not_written_to_stored_prices(client):
    """A quote is an intraday moment, not a closed daily session.

    Storing it in `asset_prices` would put a mid-session number where
    daily bars live, and `sync_daily_history` never rewrites a stored
    date - so the wrong value would be permanent (ADR-016).
    """
    headers = _auth_headers(client, email="md-owner-quote-f@example.com")
    _create_asset(client, headers, ticker="CSNA3")
    _override_provider(FakeProvider(quote=_quote("CSNA3")))

    client.get(f"{ASSETS_URL}/CSNA3/quote", headers=headers)

    stored = client.get(f"{ASSETS_URL}/CSNA3/prices", headers=headers)
    assert stored.json() == []
