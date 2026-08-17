ASSETS_URL = "/api/v1/assets"


def _auth_headers(client, email="assets-owner@example.com", password="SuperSecret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_asset_requires_authentication(client):
    response = client.post(
        ASSETS_URL,
        json={"ticker": "PETR4", "name": "Petrobras PN", "asset_type": "STOCK"},
    )
    assert response.status_code == 401


def test_create_asset_normalizes_ticker_to_uppercase(client):
    headers = _auth_headers(client)
    response = client.post(
        ASSETS_URL,
        json={"ticker": "petr4", "name": "Petrobras PN", "asset_type": "STOCK"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["ticker"] == "PETR4"
    assert data["currency"] == "BRL"
    assert data["is_active"] is True


def test_create_asset_rejects_duplicate_ticker(client):
    headers = _auth_headers(client)
    payload = {"ticker": "VALE3", "name": "Vale ON", "asset_type": "STOCK"}
    first = client.post(ASSETS_URL, json=payload, headers=headers)
    assert first.status_code == 201

    second = client.post(ASSETS_URL, json=payload, headers=headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ASSET_ALREADY_EXISTS"


def test_list_assets_returns_registered_assets(client):
    headers = _auth_headers(client)
    client.post(
        ASSETS_URL,
        json={"ticker": "ITUB4", "name": "Itau Unibanco PN", "asset_type": "STOCK"},
        headers=headers,
    )

    response = client.get(ASSETS_URL, headers=headers)
    assert response.status_code == 200
    tickers = [asset["ticker"] for asset in response.json()]
    assert "ITUB4" in tickers


def test_get_asset_by_ticker(client):
    headers = _auth_headers(client)
    client.post(
        ASSETS_URL,
        json={"ticker": "BBAS3", "name": "Banco do Brasil ON", "asset_type": "STOCK"},
        headers=headers,
    )

    response = client.get(f"{ASSETS_URL}/bbas3", headers=headers)
    assert response.status_code == 200
    assert response.json()["ticker"] == "BBAS3"


def test_get_asset_not_found(client):
    headers = _auth_headers(client)
    response = client.get(f"{ASSETS_URL}/NONEXISTENT", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"
