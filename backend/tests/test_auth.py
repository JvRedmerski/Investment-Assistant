API_PREFIX = "/api/v1/auth"


def _register(client, email="investor@example.com", password="SuperSecret123"):
    return client.post(
        f"{API_PREFIX}/register", json={"email": email, "password": password}
    )


def test_register_creates_user(client):
    response = _register(client)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "investor@example.com"
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data


def test_register_rejects_short_password(client):
    response = _register(client, password="short")
    assert response.status_code == 422


def test_register_duplicate_email_returns_conflict(client):
    first = _register(client, email="duplicate@example.com")
    assert first.status_code == 201

    second = _register(client, email="duplicate@example.com")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_login_with_valid_credentials_returns_token(client):
    _register(client, email="login@example.com", password="SuperSecret123")

    response = client.post(
        f"{API_PREFIX}/login",
        json={"email": "login@example.com", "password": "SuperSecret123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str) and len(data["access_token"]) > 0


def test_login_with_invalid_password_returns_unauthorized(client):
    _register(client, email="wrongpass@example.com", password="SuperSecret123")

    response = client.post(
        f"{API_PREFIX}/login",
        json={"email": "wrongpass@example.com", "password": "WrongPassword"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_with_unknown_email_returns_unauthorized(client):
    response = client.post(
        f"{API_PREFIX}/login",
        json={"email": "nobody@example.com", "password": "SuperSecret123"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_endpoint_requires_authentication(client):
    response = client.get(f"{API_PREFIX}/me")
    assert response.status_code == 401


def test_me_endpoint_rejects_invalid_token(client):
    response = client.get(
        f"{API_PREFIX}/me", headers={"Authorization": "Bearer invalid.token.value"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_endpoint_returns_current_user(client):
    _register(client, email="me@example.com", password="SuperSecret123")
    login_response = client.post(
        f"{API_PREFIX}/login",
        json={"email": "me@example.com", "password": "SuperSecret123"},
    )
    token = login_response.json()["access_token"]

    response = client.get(
        f"{API_PREFIX}/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_refresh_endpoint_requires_authentication(client):
    response = client.post(f"{API_PREFIX}/refresh")
    assert response.status_code == 401


def test_refresh_endpoint_issues_new_token(client):
    _register(client, email="refresh@example.com", password="SuperSecret123")
    login_response = client.post(
        f"{API_PREFIX}/login",
        json={"email": "refresh@example.com", "password": "SuperSecret123"},
    )
    old_token = login_response.json()["access_token"]

    response = client.post(
        f"{API_PREFIX}/refresh", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert response.status_code == 200
    new_token = response.json()["access_token"]
    assert isinstance(new_token, str) and len(new_token) > 0
