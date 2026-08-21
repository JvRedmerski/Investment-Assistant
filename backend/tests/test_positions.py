from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.dependencies import get_market_data_provider
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.schemas import DailyBar
from app.main import app

PORTFOLIOS_URL = "/api/v1/portfolios"
ASSETS_URL = "/api/v1/assets"


def _auth_headers(client, email="pos-owner@example.com", password="SuperSecret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_portfolio(client, headers, name="Carteira"):
    return client.post(PORTFOLIOS_URL, json={"name": name}, headers=headers).json()[
        "id"
    ]


def _create_asset(client, headers, ticker="PETR4"):
    response = client.post(
        ASSETS_URL,
        json={"ticker": ticker, "name": "Petrobras PN", "asset_type": "STOCK"},
        headers=headers,
    )
    return response.json()["id"]


def _post_transaction(client, headers, portfolio_id, **payload):
    return client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions", json=payload, headers=headers
    )


def test_positions_requires_authentication(client):
    response = client.get(f"{PORTFOLIOS_URL}/1/positions")
    assert response.status_code == 401


def test_positions_for_portfolio_with_no_transactions_is_empty(client):
    headers = _auth_headers(client)
    portfolio_id = _create_portfolio(client, headers)

    response = client.get(f"{PORTFOLIOS_URL}/{portfolio_id}/positions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["positions"] == []
    assert Decimal(data["total_invested"]) == Decimal(0)
    assert Decimal(data["net_contributions"]) == Decimal(0)


def test_positions_from_another_user_returns_not_found(client):
    owner_headers = _auth_headers(client, email="pos-owner-a@example.com")
    other_headers = _auth_headers(client, email="pos-owner-b@example.com")
    portfolio_id = _create_portfolio(client, owner_headers)

    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/positions", headers=other_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"


def test_positions_reflect_buys_sells_dividends_and_cash_flows(client):
    headers = _auth_headers(client, email="pos-owner-c@example.com")
    portfolio_id = _create_portfolio(client, headers)
    asset_id = _create_asset(client, headers, ticker="ITUB4")

    _post_transaction(
        client,
        headers,
        portfolio_id,
        type="DEPOSIT",
        quantity="5000",
        price="1",
        transaction_date="2026-01-01T00:00:00Z",
    )
    _post_transaction(
        client,
        headers,
        portfolio_id,
        asset_id=asset_id,
        type="BUY",
        quantity="10",
        price="10.00",
        fees="0",
        transaction_date="2026-01-02T00:00:00Z",
    )
    _post_transaction(
        client,
        headers,
        portfolio_id,
        asset_id=asset_id,
        type="BUY",
        quantity="10",
        price="20.00",
        fees="0",
        transaction_date="2026-01-03T00:00:00Z",
    )
    _post_transaction(
        client,
        headers,
        portfolio_id,
        asset_id=asset_id,
        type="SELL",
        quantity="5",
        price="18.00",
        fees="0",
        transaction_date="2026-01-04T00:00:00Z",
    )
    _post_transaction(
        client,
        headers,
        portfolio_id,
        asset_id=asset_id,
        type="DIVIDEND",
        quantity="15",
        price="0.50",
        transaction_date="2026-01-05T00:00:00Z",
    )

    response = client.get(f"{PORTFOLIOS_URL}/{portfolio_id}/positions", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data["positions"]) == 1
    position = data["positions"][0]
    assert position["asset_id"] == asset_id
    assert position["ticker"] == "ITUB4"
    assert Decimal(position["quantity"]) == Decimal(15)
    assert Decimal(position["average_price"]) == Decimal("15.00")
    assert Decimal(position["invested_amount"]) == Decimal("225.00")
    assert Decimal(position["realized_pnl"]) == Decimal("15.00")
    assert Decimal(position["dividends_received"]) == Decimal("7.50")

    assert Decimal(data["total_invested"]) == Decimal("225.00")
    assert Decimal(data["total_realized_pnl"]) == Decimal("15.00")
    assert Decimal(data["total_dividends_received"]) == Decimal("7.50")
    assert Decimal(data["net_contributions"]) == Decimal(5000)


# -- market value (W11-001) -------------------------------------------

_PRICE_DAYS = [
    datetime.now(UTC).date() - timedelta(days=offset) for offset in (3, 2, 1)
]


class _FakeMarketData(MarketDataProvider):
    """Three sessions of a single close, so the last one is unambiguous."""

    def __init__(self, closes):
        self._bars = [
            DailyBar(
                date=day,
                open=Decimal(close),
                high=Decimal(close),
                low=Decimal(close),
                close=Decimal(close),
                adjusted_close=Decimal(close),
                volume=Decimal(1000),
            )
            for day, close in zip(_PRICE_DAYS, closes)
        ]

    def get_quote(self, ticker):  # pragma: no cover - unused here
        raise NotImplementedError

    def get_daily_history(self, ticker, start, end):
        return [bar for bar in self._bars if start <= bar.date <= end]


@pytest.fixture(autouse=True)
def _reset_provider_override():
    yield
    app.dependency_overrides.pop(get_market_data_provider, None)


def _sync_prices(client, headers, ticker, closes):
    app.dependency_overrides[get_market_data_provider] = lambda: _FakeMarketData(closes)
    response = client.post(
        f"{ASSETS_URL}/{ticker}/prices/sync",
        json={
            "start": _PRICE_DAYS[0].isoformat(),
            "end": _PRICE_DAYS[-1].isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _positions(client, headers, portfolio_id, **params):
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/positions", params=params, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _buy(client, headers, portfolio_id, asset_id, quantity, price):
    _post_transaction(
        client,
        headers,
        portfolio_id,
        asset_id=asset_id,
        type="BUY",
        quantity=str(quantity),
        price=str(price),
        transaction_date=datetime.combine(
            _PRICE_DAYS[0], datetime.min.time()
        ).isoformat(),
    )


def test_positions_are_valued_at_the_last_stored_close(client):
    """100 shares bought at R$ 28, last printing R$ 30,82."""
    headers = _auth_headers(client, "pos-value@example.com")
    portfolio_id = _create_portfolio(client, headers)
    asset_id = _create_asset(client, headers, "PETR4")
    _sync_prices(client, headers, "PETR4", ["29.00", "30.00", "30.82"])
    _buy(client, headers, portfolio_id, asset_id, 100, "28.00")

    data = _positions(client, headers, portfolio_id)

    row = data["positions"][0]
    assert Decimal(row["last_price"]) == Decimal("30.82")
    assert row["price_date"] == _PRICE_DAYS[-1].isoformat()
    assert Decimal(row["market_value"]) == Decimal("3082.00")
    assert Decimal(row["unrealised_pnl"]) == Decimal("282.00")
    assert Decimal(data["valued_market_value"]) == Decimal("3082.00")
    assert data["unvalued_positions"] == 0


def test_a_holding_with_no_stored_price_is_reported_as_unvalued(client):
    """Not zero, and not enough to blank the rest of the table."""
    headers = _auth_headers(client, "pos-unvalued@example.com")
    portfolio_id = _create_portfolio(client, headers)
    priced = _create_asset(client, headers, "PETR4")
    unpriced = _create_asset(client, headers, "VALE3")
    _sync_prices(client, headers, "PETR4", ["29.00", "30.00", "30.82"])
    _buy(client, headers, portfolio_id, priced, 100, "28.00")
    _buy(client, headers, portfolio_id, unpriced, 50, "20.00")

    data = _positions(client, headers, portfolio_id)

    rows = {row["ticker"]: row for row in data["positions"]}
    assert rows["VALE3"]["market_value"] is None
    assert rows["VALE3"]["last_price"] is None
    assert Decimal(rows["PETR4"]["market_value"]) == Decimal("3082.00")

    assert data["unvalued_positions"] == 1
    assert Decimal(data["unvalued_invested"]) == Decimal(1000)
    # The gain is measured against the R$ 2.800 the total covers, not
    # against the R$ 3.800 the portfolio cost.
    assert Decimal(data["valued_invested"]) == Decimal(2800)
    assert Decimal(data["unrealised_pnl"]) == Decimal("282.00")
    assert Decimal(data["total_invested"]) == Decimal(3800)


def test_as_of_values_the_portfolio_at_a_past_close(client):
    """Rule 108: valuing March with today's price is look-ahead."""
    headers = _auth_headers(client, "pos-asof@example.com")
    portfolio_id = _create_portfolio(client, headers)
    asset_id = _create_asset(client, headers, "PETR4")
    _sync_prices(client, headers, "PETR4", ["29.00", "30.00", "30.82"])
    _buy(client, headers, portfolio_id, asset_id, 100, "28.00")

    data = _positions(client, headers, portfolio_id, as_of=_PRICE_DAYS[1].isoformat())

    row = data["positions"][0]
    assert Decimal(row["last_price"]) == Decimal("30.00")
    assert row["price_date"] == _PRICE_DAYS[1].isoformat()
    assert Decimal(data["valued_market_value"]) == Decimal("3000.00")


def test_as_of_truncates_the_ledger_as_well_as_the_prices(client):
    """Otherwise it prices today's holdings backwards and calls it history.

    100 shares bought three days ago and 100 more yesterday. Asked for
    the day in between, the portfolio held 100 -- not the 200 it holds
    now valued at a price from before half of them existed.
    """
    headers = _auth_headers(client, "pos-truncate@example.com")
    portfolio_id = _create_portfolio(client, headers)
    asset_id = _create_asset(client, headers, "PETR4")
    _sync_prices(client, headers, "PETR4", ["29.00", "30.00", "30.82"])
    _buy(client, headers, portfolio_id, asset_id, 100, "28.00")
    _post_transaction(
        client,
        headers,
        portfolio_id,
        asset_id=asset_id,
        type="BUY",
        quantity="100",
        price="30.00",
        transaction_date=datetime.combine(
            _PRICE_DAYS[2], datetime.min.time()
        ).isoformat(),
    )

    at_middle = _positions(
        client, headers, portfolio_id, as_of=_PRICE_DAYS[1].isoformat()
    )
    latest = _positions(client, headers, portfolio_id)

    assert Decimal(at_middle["positions"][0]["quantity"]) == Decimal(100)
    assert Decimal(at_middle["valued_market_value"]) == Decimal("3000.00")
    assert Decimal(latest["positions"][0]["quantity"]) == Decimal(200)
    assert Decimal(latest["valued_market_value"]) == Decimal("6164.00")


def test_the_price_window_is_reported(client):
    headers = _auth_headers(client, "pos-window@example.com")
    portfolio_id = _create_portfolio(client, headers)
    asset_id = _create_asset(client, headers, "PETR4")
    _sync_prices(client, headers, "PETR4", ["29.00", "30.00", "30.82"])
    _buy(client, headers, portfolio_id, asset_id, 100, "28.00")

    data = _positions(client, headers, portfolio_id)

    assert data["oldest_price_date"] == _PRICE_DAYS[-1].isoformat()
    assert data["newest_price_date"] == _PRICE_DAYS[-1].isoformat()


def test_an_empty_portfolio_reports_no_price_window(client):
    headers = _auth_headers(client, "pos-empty@example.com")
    portfolio_id = _create_portfolio(client, headers)

    data = _positions(client, headers, portfolio_id)

    assert Decimal(data["valued_market_value"]) == Decimal(0)
    assert data["oldest_price_date"] is None
