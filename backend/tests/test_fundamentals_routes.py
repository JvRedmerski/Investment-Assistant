"""Integration tests for the fundamentals sync/read endpoints, overriding
get_fundamentals_provider with a fake so nothing hits the network."""

from datetime import date
from decimal import Decimal

import pytest

from app.api.dependencies import get_fundamentals_provider
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.exceptions import (
    FundamentalsNotFoundError,
    FundamentalsUnavailableError,
    InvalidFundamentalsResponseError,
)
from app.integrations.fundamentals.schemas import FinancialStatement
from app.main import app

ASSETS_URL = "/api/v1/assets"


class FakeProvider(FundamentalsProvider):
    def __init__(self, statements=None, error=None):
        self._statements = statements or []
        self._error = error

    def get_annual_statements(self, ticker):
        if self._error is not None:
            raise self._error
        return list(self._statements)

    def close(self):
        pass


class ExplodingProvider(FundamentalsProvider):
    """Proves the read path never reaches the provider."""

    def get_annual_statements(self, ticker):
        raise AssertionError("the read path must not call the provider")

    def close(self):
        pass


def _statement(year: int, revenue: str = "100") -> FinancialStatement:
    return FinancialStatement(
        reference_date=date(year, 12, 31),
        revenue=Decimal(revenue),
        net_income=Decimal(10),
        equity=Decimal(500),
        debt=Decimal(300),
        cash=Decimal(60),
    )


@pytest.fixture(autouse=True)
def _reset_provider_override():
    yield
    app.dependency_overrides.pop(get_fundamentals_provider, None)


def _override_provider(provider: FundamentalsProvider) -> None:
    app.dependency_overrides[get_fundamentals_provider] = lambda: provider


def _auth_headers(client, email="fund-owner@example.com", password="SuperSecret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_asset(client, headers, ticker="PETR4"):
    return client.post(
        ASSETS_URL,
        json={"ticker": ticker, "name": "Petrobras PN", "asset_type": "STOCK"},
        headers=headers,
    ).json()


def test_sync_requires_authentication(client):
    response = client.post(f"{ASSETS_URL}/PETR4/fundamentals/sync")
    assert response.status_code == 401


def test_read_requires_authentication(client):
    response = client.get(f"{ASSETS_URL}/PETR4/fundamentals")
    assert response.status_code == 401


def test_sync_returns_not_found_for_unregistered_asset(client):
    headers = _auth_headers(client)
    _override_provider(FakeProvider([_statement(2024)]))

    response = client.post(f"{ASSETS_URL}/NOPE3/fundamentals/sync", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_sync_then_read_returns_stored_statements(client):
    headers = _auth_headers(client)
    _create_asset(client, headers)
    _override_provider(FakeProvider([_statement(2023), _statement(2024)]))

    sync = client.post(f"{ASSETS_URL}/PETR4/fundamentals/sync", headers=headers)

    assert sync.status_code == 200
    assert sync.json() == {
        "ticker": "PETR4",
        "fetched": 2,
        "inserted": 2,
        "skipped_existing": 0,
        "rejected": 0,
        "refilled": 0,
    }

    # Swap in a provider that would fail loudly if the read path used it.
    _override_provider(ExplodingProvider())
    read = client.get(f"{ASSETS_URL}/PETR4/fundamentals", headers=headers)

    assert read.status_code == 200
    body = read.json()
    assert [row["reference_date"] for row in body] == ["2023-12-31", "2024-12-31"]
    assert body[0]["revenue"] == "100.0000"
    assert body[0]["ebitda"] is None


def test_read_supports_reference_date_filtering(client):
    headers = _auth_headers(client)
    _create_asset(client, headers)
    _override_provider(
        FakeProvider([_statement(2022), _statement(2023), _statement(2024)])
    )
    client.post(f"{ASSETS_URL}/PETR4/fundamentals/sync", headers=headers)

    response = client.get(
        f"{ASSETS_URL}/PETR4/fundamentals",
        params={"start": "2023-01-01", "end": "2023-12-31"},
        headers=headers,
    )

    assert [row["reference_date"] for row in response.json()] == ["2023-12-31"]


def test_repeated_sync_through_the_api_is_idempotent(client):
    headers = _auth_headers(client)
    _create_asset(client, headers)
    _override_provider(FakeProvider([_statement(2024)]))

    client.post(f"{ASSETS_URL}/PETR4/fundamentals/sync", headers=headers)
    second = client.post(f"{ASSETS_URL}/PETR4/fundamentals/sync", headers=headers)

    assert second.json()["inserted"] == 0
    assert second.json()["skipped_existing"] == 1
    assert (
        len(client.get(f"{ASSETS_URL}/PETR4/fundamentals", headers=headers).json()) == 1
    )


def test_read_on_asset_without_fundamentals_returns_empty_list(client):
    headers = _auth_headers(client)
    _create_asset(client, headers)

    response = client.get(f"{ASSETS_URL}/PETR4/fundamentals", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (FundamentalsNotFoundError("nope"), 404, "FUNDAMENTALS_NOT_FOUND"),
        (FundamentalsUnavailableError("down"), 503, "FUNDAMENTALS_UNAVAILABLE"),
        (
            InvalidFundamentalsResponseError("garbage"),
            502,
            "FUNDAMENTALS_INVALID_RESPONSE",
        ),
    ],
)
def test_provider_errors_map_to_expected_http_status(
    client, error, expected_status, expected_code
):
    headers = _auth_headers(client)
    _create_asset(client, headers)
    _override_provider(FakeProvider(error=error))

    response = client.post(f"{ASSETS_URL}/PETR4/fundamentals/sync", headers=headers)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
