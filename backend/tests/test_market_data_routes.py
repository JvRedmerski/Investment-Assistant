"""Integration tests for the price sync/read endpoints, overriding
get_market_data_provider with a fake so nothing hits the network."""

from datetime import date
from decimal import Decimal

import pytest

from app.api.dependencies import get_market_data_provider
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import DailyBar
from app.main import app

ASSETS_URL = "/api/v1/assets"


class FakeProvider(MarketDataProvider):
    def __init__(self, bars=None, error=None):
        self._bars = bars or []
        self._error = error

    def get_quote(self, ticker):  # pragma: no cover - unused here
        raise NotImplementedError

    def get_daily_history(self, ticker, start, end):
        if self._error is not None:
            raise self._error
        return [bar for bar in self._bars if start <= bar.date <= end]


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
