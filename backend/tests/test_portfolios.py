PORTFOLIOS_URL = "/api/v1/portfolios"


def _auth_headers(
    client, email="portfolio-owner@example.com", password="SuperSecret123"
):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_portfolio_requires_authentication(client):
    response = client.post(PORTFOLIOS_URL, json={"name": "Carteira Principal"})
    assert response.status_code == 401


def test_create_and_get_portfolio(client):
    headers = _auth_headers(client)
    create = client.post(
        PORTFOLIOS_URL, json={"name": "Carteira Conservadora"}, headers=headers
    )
    assert create.status_code == 201
    portfolio_id = create.json()["id"]
    assert create.json()["name"] == "Carteira Conservadora"

    get_response = client.get(f"{PORTFOLIOS_URL}/{portfolio_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == portfolio_id


def test_list_portfolios_only_returns_own_portfolios(client):
    owner_headers = _auth_headers(client, email="owner-a@example.com")
    other_headers = _auth_headers(client, email="owner-b@example.com")

    client.post(
        PORTFOLIOS_URL, json={"name": "Owner A Portfolio"}, headers=owner_headers
    )
    client.post(
        PORTFOLIOS_URL, json={"name": "Owner B Portfolio"}, headers=other_headers
    )

    response = client.get(PORTFOLIOS_URL, headers=owner_headers)
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert names == ["Owner A Portfolio"]


def test_get_portfolio_from_another_user_returns_not_found(client):
    owner_headers = _auth_headers(client, email="owner-c@example.com")
    other_headers = _auth_headers(client, email="owner-d@example.com")

    create = client.post(
        PORTFOLIOS_URL, json={"name": "Private Portfolio"}, headers=owner_headers
    )
    portfolio_id = create.json()["id"]

    response = client.get(f"{PORTFOLIOS_URL}/{portfolio_id}", headers=other_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"


def test_update_portfolio_name(client):
    headers = _auth_headers(client, email="owner-e@example.com")
    create = client.post(PORTFOLIOS_URL, json={"name": "Old Name"}, headers=headers)
    portfolio_id = create.json()["id"]

    response = client.patch(
        f"{PORTFOLIOS_URL}/{portfolio_id}", json={"name": "New Name"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_delete_portfolio(client):
    headers = _auth_headers(client, email="owner-f@example.com")
    create = client.post(PORTFOLIOS_URL, json={"name": "To Delete"}, headers=headers)
    portfolio_id = create.json()["id"]

    delete_response = client.delete(f"{PORTFOLIOS_URL}/{portfolio_id}", headers=headers)
    assert delete_response.status_code == 204

    get_response = client.get(f"{PORTFOLIOS_URL}/{portfolio_id}", headers=headers)
    assert get_response.status_code == 404
