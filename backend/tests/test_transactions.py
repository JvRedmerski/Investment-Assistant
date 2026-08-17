from decimal import Decimal

PORTFOLIOS_URL = "/api/v1/portfolios"
ASSETS_URL = "/api/v1/assets"


def _auth_headers(client, email="tx-owner@example.com", password="SuperSecret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_portfolio(client, headers, name="Carteira"):
    response = client.post(PORTFOLIOS_URL, json={"name": name}, headers=headers)
    return response.json()["id"]


def _create_asset(client, headers, ticker="PETR4"):
    response = client.post(
        ASSETS_URL,
        json={"ticker": ticker, "name": "Petrobras PN", "asset_type": "STOCK"},
        headers=headers,
    )
    return response.json()["id"]


def test_create_transaction_requires_authentication(client):
    response = client.post(f"{PORTFOLIOS_URL}/1/transactions", json={})
    assert response.status_code == 401


def test_create_buy_transaction(client):
    headers = _auth_headers(client)
    portfolio_id = _create_portfolio(client, headers)
    asset_id = _create_asset(client, headers)

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": "100",
            "price": "38.50",
            "fees": "5.00",
            "transaction_date": "2026-01-10T13:00:00Z",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "BUY"
    assert Decimal(data["quantity"]) == Decimal(100)
    assert data["portfolio_id"] == portfolio_id


def test_create_transaction_on_foreign_portfolio_returns_not_found(client):
    owner_headers = _auth_headers(client, email="tx-owner-a@example.com")
    other_headers = _auth_headers(client, email="tx-owner-b@example.com")
    portfolio_id = _create_portfolio(client, owner_headers)
    asset_id = _create_asset(client, owner_headers, ticker="VALE3")

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": "10",
            "price": "60.00",
            "transaction_date": "2026-01-10T13:00:00Z",
        },
        headers=other_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"


def test_create_transaction_with_unknown_asset_returns_not_found(client):
    headers = _auth_headers(client, email="tx-owner-c@example.com")
    portfolio_id = _create_portfolio(client, headers)

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": 999999,
            "type": "BUY",
            "quantity": "10",
            "price": "60.00",
            "transaction_date": "2026-01-10T13:00:00Z",
        },
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_deposit_transaction_requires_no_asset_id(client):
    headers = _auth_headers(client, email="tx-owner-d@example.com")
    portfolio_id = _create_portfolio(client, headers)

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "type": "DEPOSIT",
            "quantity": "1000",
            "price": "1",
            "transaction_date": "2026-01-01T00:00:00Z",
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["asset_id"] is None


def test_buy_transaction_without_asset_id_is_rejected(client):
    headers = _auth_headers(client, email="tx-owner-e@example.com")
    portfolio_id = _create_portfolio(client, headers)

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "type": "BUY",
            "quantity": "10",
            "price": "60.00",
            "transaction_date": "2026-01-10T13:00:00Z",
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_sell_more_than_held_quantity_is_rejected(client):
    headers = _auth_headers(client, email="tx-owner-f@example.com")
    portfolio_id = _create_portfolio(client, headers)
    asset_id = _create_asset(client, headers, ticker="ITUB4")

    client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": "10",
            "price": "30.00",
            "transaction_date": "2026-01-10T13:00:00Z",
        },
        headers=headers,
    )

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "SELL",
            "quantity": "11",
            "price": "31.00",
            "transaction_date": "2026-01-11T13:00:00Z",
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_POSITION"


def test_sell_up_to_held_quantity_is_accepted(client):
    headers = _auth_headers(client, email="tx-owner-g@example.com")
    portfolio_id = _create_portfolio(client, headers)
    asset_id = _create_asset(client, headers, ticker="BBAS3")

    client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": "10",
            "price": "30.00",
            "transaction_date": "2026-01-10T13:00:00Z",
        },
        headers=headers,
    )

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "SELL",
            "quantity": "10",
            "price": "31.00",
            "transaction_date": "2026-01-11T13:00:00Z",
        },
        headers=headers,
    )
    assert response.status_code == 201


def test_list_transactions_returns_them_in_chronological_order(client):
    headers = _auth_headers(client, email="tx-owner-h@example.com")
    portfolio_id = _create_portfolio(client, headers)
    asset_id = _create_asset(client, headers, ticker="WEGE3")

    client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": "5",
            "price": "40.00",
            "transaction_date": "2026-02-01T13:00:00Z",
        },
        headers=headers,
    )
    client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": "5",
            "price": "42.00",
            "transaction_date": "2026-01-01T13:00:00Z",
        },
        headers=headers,
    )

    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions", headers=headers
    )
    assert response.status_code == 200
    dates = [item["transaction_date"] for item in response.json()]
    assert dates == sorted(dates)
