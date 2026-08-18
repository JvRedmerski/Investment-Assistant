"""Integration tests for the benchmark endpoints, overriding
get_benchmark_provider with a fake so nothing hits the network."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.dependencies import get_benchmark_provider
from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.exceptions import (
    BenchmarkSeriesNotFoundError,
    BenchmarkUnavailableError,
    InvalidBenchmarkResponseError,
)
from app.integrations.benchmarks.schemas import BenchmarkObservation
from app.main import app

BENCHMARKS_URL = "/api/v1/benchmarks"


class FakeProvider(BenchmarkProvider):
    def __init__(self, observations=None, error=None):
        self._observations = observations or []
        self._error = error

    def get_series(self, series_id, start, end, kind):
        if self._error is not None:
            raise self._error
        return [
            observation
            for observation in self._observations
            if start <= observation.date <= end
        ]


def _observation(day: date, value: str) -> BenchmarkObservation:
    return BenchmarkObservation(date=day, value=Decimal(value))


def _settled_days(count: int) -> list[BenchmarkObservation]:
    """Observations old enough that no incomplete-period rule fires."""
    first = datetime.now(UTC).date() - timedelta(days=60)
    return [
        _observation(first + timedelta(days=offset), "0.00043739")
        for offset in range(count)
    ]


@pytest.fixture(autouse=True)
def _reset_provider_override():
    yield
    app.dependency_overrides.pop(get_benchmark_provider, None)


def _override_provider(provider: FakeProvider) -> None:
    app.dependency_overrides[get_benchmark_provider] = lambda: provider


def _auth_headers(client, email="bm-owner@example.com", password="SuperSecret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_listing_benchmarks_requires_authentication(client):
    assert client.get(BENCHMARKS_URL).status_code == 401


def test_the_catalog_lists_the_benchmarks_the_roadmap_asks_for(client):
    headers = _auth_headers(client)

    response = client.get(BENCHMARKS_URL, headers=headers)

    assert response.status_code == 200
    by_code = {entry["code"]: entry for entry in response.json()}
    assert {"CDI", "IBOV", "IPCA"} <= set(by_code)
    assert by_code["CDI"]["kind"] == "RATE"
    assert by_code["CDI"]["periodicity"] == "DAILY"
    assert by_code["IBOV"]["kind"] == "INDEX"
    assert by_code["IPCA"]["periodicity"] == "MONTHLY"


def test_sync_requires_authentication(client):
    assert client.post(f"{BENCHMARKS_URL}/CDI/sync", json={}).status_code == 401


def test_an_unknown_benchmark_code_is_a_404(client):
    headers = _auth_headers(client, email="bm-unknown@example.com")

    response = client.post(f"{BENCHMARKS_URL}/NOPE/sync", json={}, headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BENCHMARK_NOT_FOUND"


def test_a_benchmark_code_is_matched_case_insensitively(client):
    headers = _auth_headers(client, email="bm-case@example.com")
    _override_provider(FakeProvider(_settled_days(2)))

    response = client.post(f"{BENCHMARKS_URL}/cdi/sync", json={}, headers=headers)

    assert response.status_code == 200
    assert response.json()["code"] == "CDI"


def test_sync_stores_the_series_and_the_read_endpoint_never_calls_the_source(client):
    headers = _auth_headers(client, email="bm-owner-a@example.com")
    observations = _settled_days(3)
    _override_provider(FakeProvider(observations))

    sync = client.post(
        f"{BENCHMARKS_URL}/CDI/sync",
        json={
            "start": observations[0].date.isoformat(),
            "end": observations[-1].date.isoformat(),
        },
        headers=headers,
    )

    assert sync.status_code == 200
    assert sync.json()["fetched"] == 3
    assert sync.json()["inserted"] == 3

    # A provider that would blow up if touched, proving the read path
    # only queries the database (AGENTS.md rule 23).
    class ExplodingProvider(BenchmarkProvider):
        def get_series(self, series_id, start, end, kind):  # pragma: no cover
            raise AssertionError("the read path must not call the source")

    _override_provider(ExplodingProvider())
    values = client.get(f"{BENCHMARKS_URL}/CDI/values", headers=headers)

    assert values.status_code == 200
    body = values.json()
    assert len(body) == 3
    assert body[0]["benchmark_code"] == "CDI"
    assert Decimal(body[0]["value"]) == Decimal("0.00043739")


def test_reading_values_accepts_a_window(client):
    headers = _auth_headers(client, email="bm-window@example.com")
    observations = _settled_days(4)
    _override_provider(FakeProvider(observations))
    client.post(f"{BENCHMARKS_URL}/CDI/sync", json={}, headers=headers)

    response = client.get(
        f"{BENCHMARKS_URL}/CDI/values",
        params={
            "start": observations[1].date.isoformat(),
            "end": observations[2].date.isoformat(),
        },
        headers=headers,
    )

    assert [entry["date"] for entry in response.json()] == [
        observations[1].date.isoformat(),
        observations[2].date.isoformat(),
    ]


def test_reading_an_unknown_benchmark_is_a_404(client):
    headers = _auth_headers(client, email="bm-read-unknown@example.com")

    response = client.get(f"{BENCHMARKS_URL}/NOPE/values", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BENCHMARK_NOT_FOUND"


def test_a_start_after_the_end_is_rejected_before_any_call(client):
    headers = _auth_headers(client, email="bm-range@example.com")
    _override_provider(FakeProvider())

    response = client.post(
        f"{BENCHMARKS_URL}/CDI/sync",
        json={"start": "2024-02-01", "end": "2024-01-01"},
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (BenchmarkSeriesNotFoundError("gone"), 404, "BENCHMARK_SERIES_NOT_FOUND"),
        (BenchmarkUnavailableError("down"), 503, "BENCHMARK_SOURCE_UNAVAILABLE"),
        (InvalidBenchmarkResponseError("html"), 502, "BENCHMARK_INVALID_RESPONSE"),
    ],
)
def test_source_failures_map_to_the_shared_error_envelope(
    client, error, expected_status, expected_code
):
    headers = _auth_headers(client, email=f"bm-{expected_status}@example.com")
    _override_provider(FakeProvider(error=error))

    response = client.post(f"{BENCHMARKS_URL}/CDI/sync", json={}, headers=headers)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
