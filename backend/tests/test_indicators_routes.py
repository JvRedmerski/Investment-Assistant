"""Integration tests for the indicator compute/read endpoints."""

from datetime import date
from decimal import Decimal

import pytest

from app.api.dependencies import get_fundamentals_provider
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.schemas import FinancialStatement
from app.main import app

ASSETS_URL = "/api/v1/assets"


class FakeProvider(FundamentalsProvider):
    def __init__(self, statements):
        self._statements = statements

    def get_annual_statements(self, ticker):
        return list(self._statements)

    def close(self):
        pass


def _statement(year: int, revenue: str) -> FinancialStatement:
    return FinancialStatement(
        reference_date=date(year, 12, 31),
        revenue=Decimal(revenue),
        net_income=Decimal(150),
        equity=Decimal(600),
        debt=Decimal(400),
        cash=Decimal(100),
    )


@pytest.fixture(autouse=True)
def _reset_provider_override():
    yield
    app.dependency_overrides.pop(get_fundamentals_provider, None)


def _auth_headers(client, email="ind-owner@example.com", password="SuperSecret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed_asset_with_statements(client, headers):
    client.post(
        ASSETS_URL,
        json={"ticker": "PETR4", "name": "Petrobras PN", "asset_type": "STOCK"},
        headers=headers,
    )
    app.dependency_overrides[get_fundamentals_provider] = lambda: FakeProvider(
        [_statement(2023, "800"), _statement(2024, "1000")]
    )
    client.post(f"{ASSETS_URL}/PETR4/fundamentals/sync", headers=headers)


def test_compute_requires_authentication(client):
    assert client.post(f"{ASSETS_URL}/PETR4/indicators/compute").status_code == 401


def test_read_requires_authentication(client):
    assert client.get(f"{ASSETS_URL}/PETR4/indicators").status_code == 401


def test_compute_returns_not_found_for_unregistered_asset(client):
    headers = _auth_headers(client)

    response = client.post(f"{ASSETS_URL}/NOPE3/indicators/compute", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_compute_then_read_returns_derived_indicators(client):
    headers = _auth_headers(client)
    _seed_asset_with_statements(client, headers)

    compute = client.post(f"{ASSETS_URL}/PETR4/indicators/compute", headers=headers)

    assert compute.status_code == 200
    assert compute.json() == {
        "ticker": "PETR4",
        "periods": 2,
        "computed": 2,
        "skipped_existing": 0,
        "recomputed": False,
    }

    read = client.get(f"{ASSETS_URL}/PETR4/indicators", headers=headers)

    assert read.status_code == 200
    body = read.json()
    assert [row["reference_date"] for row in body] == ["2023-12-31", "2024-12-31"]
    assert body[1]["roe"] == 0.25
    assert body[1]["revenue_growth"] == 0.25
    assert body[1]["pe"] is None


def test_repeated_compute_through_the_api_is_idempotent(client):
    headers = _auth_headers(client)
    _seed_asset_with_statements(client, headers)
    client.post(f"{ASSETS_URL}/PETR4/indicators/compute", headers=headers)

    second = client.post(f"{ASSETS_URL}/PETR4/indicators/compute", headers=headers)

    assert second.json()["computed"] == 0
    assert second.json()["skipped_existing"] == 2
    assert (
        len(client.get(f"{ASSETS_URL}/PETR4/indicators", headers=headers).json()) == 2
    )


def test_read_supports_reference_date_filtering(client):
    headers = _auth_headers(client)
    _seed_asset_with_statements(client, headers)
    client.post(f"{ASSETS_URL}/PETR4/indicators/compute", headers=headers)

    response = client.get(
        f"{ASSETS_URL}/PETR4/indicators",
        params={"start": "2024-01-01"},
        headers=headers,
    )

    assert [row["reference_date"] for row in response.json()] == ["2024-12-31"]


def test_compute_on_asset_without_statements_returns_zero_counts(client):
    headers = _auth_headers(client)
    client.post(
        ASSETS_URL,
        json={"ticker": "VALE3", "name": "Vale ON", "asset_type": "STOCK"},
        headers=headers,
    )

    response = client.post(f"{ASSETS_URL}/VALE3/indicators/compute", headers=headers)

    assert response.json() == {
        "ticker": "VALE3",
        "periods": 0,
        "computed": 0,
        "skipped_existing": 0,
        "recomputed": False,
    }
    assert client.get(f"{ASSETS_URL}/VALE3/indicators", headers=headers).json() == []


def test_recompute_rebuilds_stored_indicators(client):
    headers = _auth_headers(client)
    _seed_asset_with_statements(client, headers)
    client.post(f"{ASSETS_URL}/PETR4/indicators/compute", headers=headers)

    response = client.post(
        f"{ASSETS_URL}/PETR4/indicators/compute",
        params={"recompute": "true"},
        headers=headers,
    )

    body = response.json()
    assert body["recomputed"] is True
    assert body["computed"] == 2
    assert body["skipped_existing"] == 0
    # Rebuilt, not duplicated.
    assert (
        len(client.get(f"{ASSETS_URL}/PETR4/indicators", headers=headers).json()) == 2
    )
