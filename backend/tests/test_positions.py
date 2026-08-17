from decimal import Decimal

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
