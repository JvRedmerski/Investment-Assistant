"""End-to-end tests for the comparison endpoints.

These go through the whole chain — register, buy, sync prices, sync the
benchmark, compare — with fake providers so nothing touches the network.
The point is to prove the wiring holds together, since every individual
calculation is already pinned by the pure tests.

Dates are generated relative to today rather than hard-coded, so the
incomplete-period rule never fires by accident on the day the suite runs.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.dependencies import get_benchmark_provider, get_market_data_provider
from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.schemas import BenchmarkObservation
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.schemas import DailyBar
from app.main import app

ASSETS_URL = "/api/v1/assets"
BENCHMARKS_URL = "/api/v1/benchmarks"
PORTFOLIOS_URL = "/api/v1/portfolios"

#: Five settled consecutive days, ending well before today.
DAYS = [datetime.now(UTC).date() - timedelta(days=60 - offset) for offset in range(5)]

#: An asset that rose 20% over the window: 100 -> 105 -> 110 -> 115 -> 120.
ASSET_LEVELS = ["100", "105", "110", "115", "120"]

#: An index that rose 10% over the same window.
INDEX_LEVELS = ["1000", "1025", "1050", "1075", "1100"]

#: A flat daily rate. Four compounding steps of 1% give 1.01**4 - 1.
DAILY_RATE = Decimal("0.01")


class FakeMarketData(MarketDataProvider):
    def __init__(self, levels):
        self._bars = [
            DailyBar(
                date=day,
                open=Decimal(level),
                high=Decimal(level),
                low=Decimal(level),
                close=Decimal(level),
                adjusted_close=Decimal(level),
                volume=Decimal(1000),
            )
            for day, level in zip(DAYS, levels)
        ]

    def get_quote(self, ticker):  # pragma: no cover - unused here
        raise NotImplementedError

    def get_daily_history(self, ticker, start, end):
        return [bar for bar in self._bars if start <= bar.date <= end]


class FakeBenchmark(BenchmarkProvider):
    def __init__(self, values):
        self._observations = [
            BenchmarkObservation(date=day, value=Decimal(str(value)))
            for day, value in zip(DAYS, values)
        ]

    def get_series(self, series_id, start, end, kind):
        return [
            observation
            for observation in self._observations
            if start <= observation.date <= end
        ]


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.pop(get_benchmark_provider, None)
    app.dependency_overrides.pop(get_market_data_provider, None)


def _auth_headers(client, email):
    client.post(
        "/api/v1/auth/register", json={"email": email, "password": "SuperSecret123"}
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _window():
    return {"start": DAYS[0].isoformat(), "end": DAYS[-1].isoformat()}


def _seed_asset(client, headers, ticker, levels):
    client.post(
        ASSETS_URL,
        json={"ticker": ticker, "name": ticker, "asset_type": "STOCK"},
        headers=headers,
    )
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketData(levels)
    response = client.post(
        f"{ASSETS_URL}/{ticker}/prices/sync", json=_window(), headers=headers
    )
    assert response.json()["inserted"] == len(levels)
    return client.get(f"{ASSETS_URL}/{ticker}", headers=headers).json()["id"]


def _seed_benchmark(client, headers, code, values):
    app.dependency_overrides[get_benchmark_provider] = lambda: FakeBenchmark(values)
    response = client.post(
        f"{BENCHMARKS_URL}/{code}/sync", json=_window(), headers=headers
    )
    assert response.status_code == 200
    return response.json()


def _seed_portfolio(client, headers, asset_id, quantity="10", price="100", day=0):
    portfolio_id = client.post(
        PORTFOLIOS_URL, json={"name": "Main"}, headers=headers
    ).json()["id"]
    client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": quantity,
            "price": price,
            "transaction_date": datetime.combine(
                DAYS[day], datetime.min.time()
            ).isoformat(),
        },
        headers=headers,
    )
    return portfolio_id


# -- asset against a benchmark ---------------------------------------


def test_an_asset_is_compared_against_the_ibovespa(client):
    headers = _auth_headers(client, "cmp-asset@example.com")
    _seed_asset(client, headers, "PETR4", ASSET_LEVELS)
    _seed_benchmark(client, headers, "IBOV", INDEX_LEVELS)

    response = client.get(
        f"{ASSETS_URL}/PETR4/benchmarks/IBOV", params=_window(), headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_code"] == "IBOV"
    assert Decimal(body["subject"]["total_return"]) == Decimal("0.2")
    assert Decimal(body["benchmark"]["total_return"]) == Decimal("0.1")
    assert Decimal(body["excess_return"]) == Decimal("0.1")
    assert Decimal(body["return_ratio"]) == Decimal(2)


def test_an_asset_is_compared_against_the_cdi(client):
    """A rate benchmark is compounded into a level before comparing.

    Four steps of 1% give 1.01 ** 4 - 1 = 4.060401%, which is what the
    accumulated index must report — not a comparison of one rate against
    another.
    """
    headers = _auth_headers(client, "cmp-cdi@example.com")
    _seed_asset(client, headers, "VALE3", ASSET_LEVELS)
    _seed_benchmark(client, headers, "CDI", [DAILY_RATE] * len(DAYS))

    response = client.get(
        f"{ASSETS_URL}/VALE3/benchmarks/CDI", params=_window(), headers=headers
    )

    body = response.json()
    expected = Decimal("1.01") ** 4 - 1
    assert Decimal(body["benchmark"]["total_return"]) == expected
    # Beta against a rate is refused by design.
    assert body["beta"] is None
    # The CDI was ingested, so the risk-adjusted ratios are computable.
    assert body["risk_free_rate"] is not None
    assert body["sharpe"] is not None


def test_the_risk_free_rate_is_absent_until_the_cdi_is_ingested(client):
    headers = _auth_headers(client, "cmp-norf@example.com")
    _seed_asset(client, headers, "ITUB4", ASSET_LEVELS)
    _seed_benchmark(client, headers, "IBOV", INDEX_LEVELS)

    body = client.get(
        f"{ASSETS_URL}/ITUB4/benchmarks/IBOV", params=_window(), headers=headers
    ).json()

    assert body["risk_free_rate"] is None
    assert body["sharpe"] is None
    assert body["sortino"] is None


# -- portfolio against a benchmark -----------------------------------


def test_a_portfolio_is_compared_against_the_ibovespa(client):
    """The portfolio holds one asset, so its index tracks that asset."""
    headers = _auth_headers(client, "cmp-pf@example.com")
    asset_id = _seed_asset(client, headers, "BBAS3", ASSET_LEVELS)
    _seed_benchmark(client, headers, "IBOV", INDEX_LEVELS)
    portfolio_id = _seed_portfolio(client, headers, asset_id)

    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/benchmarks/IBOV",
        params=_window(),
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["subject"]["total_return"]) == Decimal("0.2")
    assert Decimal(body["excess_return"]) == Decimal("0.1")


def test_a_contribution_does_not_make_the_portfolio_beat_the_benchmark(client):
    """The claim the whole wave rests on, checked end to end.

    Two portfolios hold the same asset over the same window; the second
    adds a second purchase midway. Its patrimonial growth is far larger,
    and its measured performance is identical — which is the only reason
    a portfolio can be set against an index at all.
    """
    headers = _auth_headers(client, "cmp-twr@example.com")
    asset_id = _seed_asset(client, headers, "WEGE3", ASSET_LEVELS)
    _seed_benchmark(client, headers, "IBOV", INDEX_LEVELS)

    steady = _seed_portfolio(client, headers, asset_id)
    contributing = _seed_portfolio(client, headers, asset_id)
    client.post(
        f"{PORTFOLIOS_URL}/{contributing}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": "40",
            "price": "110",
            "transaction_date": datetime.combine(
                DAYS[2], datetime.min.time()
            ).isoformat(),
        },
        headers=headers,
    )

    steady_body = client.get(
        f"{PORTFOLIOS_URL}/{steady}/benchmarks/IBOV",
        params=_window(),
        headers=headers,
    ).json()
    contributing_body = client.get(
        f"{PORTFOLIOS_URL}/{contributing}/benchmarks/IBOV",
        params=_window(),
        headers=headers,
    ).json()

    assert (
        contributing_body["subject"]["total_return"]
        == steady_body["subject"]["total_return"]
    )
    assert Decimal(contributing_body["subject"]["total_return"]) == Decimal("0.2")


def test_a_portfolio_with_no_prices_reports_nothing_rather_than_zero(client):
    headers = _auth_headers(client, "cmp-empty@example.com")
    client.post(
        ASSETS_URL,
        json={"ticker": "MGLU3", "name": "MGLU3", "asset_type": "STOCK"},
        headers=headers,
    )
    asset_id = client.get(f"{ASSETS_URL}/MGLU3", headers=headers).json()["id"]
    _seed_benchmark(client, headers, "IBOV", INDEX_LEVELS)
    portfolio_id = _seed_portfolio(client, headers, asset_id)

    body = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/benchmarks/IBOV",
        params=_window(),
        headers=headers,
    ).json()

    assert body["subject"]["observations"] == 0
    assert body["subject"]["total_return"] is None
    assert body["excess_return"] is None


# -- guards ----------------------------------------------------------


def test_comparison_requires_authentication(client):
    assert client.get(f"{ASSETS_URL}/PETR4/benchmarks/IBOV").status_code == 401
    assert client.get(f"{PORTFOLIOS_URL}/1/benchmarks/IBOV").status_code == 401


def test_an_unknown_benchmark_is_a_404_on_both_endpoints(client):
    headers = _auth_headers(client, "cmp-404@example.com")
    asset_id = _seed_asset(client, headers, "RENT3", ASSET_LEVELS)
    portfolio_id = _seed_portfolio(client, headers, asset_id)

    asset_response = client.get(f"{ASSETS_URL}/RENT3/benchmarks/NOPE", headers=headers)
    portfolio_response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/benchmarks/NOPE", headers=headers
    )

    assert asset_response.status_code == 404
    assert asset_response.json()["error"]["code"] == "BENCHMARK_NOT_FOUND"
    assert portfolio_response.status_code == 404


def test_another_users_portfolio_cannot_be_compared(client):
    owner = _auth_headers(client, "cmp-owner@example.com")
    asset_id = _seed_asset(client, owner, "CSNA3", ASSET_LEVELS)
    portfolio_id = _seed_portfolio(client, owner, asset_id)

    intruder = _auth_headers(client, "cmp-intruder@example.com")
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/benchmarks/IBOV", headers=intruder
    )

    assert response.status_code == 404


def test_the_comparison_never_calls_an_external_source(client):
    """Reading is a database operation (AGENTS.md rule 23)."""
    headers = _auth_headers(client, "cmp-noio@example.com")
    _seed_asset(client, headers, "SUZB3", ASSET_LEVELS)
    _seed_benchmark(client, headers, "IBOV", INDEX_LEVELS)

    class ExplodingBenchmark(BenchmarkProvider):
        def get_series(self, series_id, start, end, kind):  # pragma: no cover
            raise AssertionError("comparison must not call the source")

    class ExplodingMarketData(MarketDataProvider):
        def get_quote(self, ticker):  # pragma: no cover
            raise AssertionError("comparison must not call the source")

        def get_daily_history(self, ticker, start, end):  # pragma: no cover
            raise AssertionError("comparison must not call the source")

    app.dependency_overrides[get_benchmark_provider] = lambda: ExplodingBenchmark()
    app.dependency_overrides[get_market_data_provider] = lambda: ExplodingMarketData()

    response = client.get(
        f"{ASSETS_URL}/SUZB3/benchmarks/IBOV", params=_window(), headers=headers
    )

    assert response.status_code == 200


def test_the_measured_window_is_reported_not_the_one_requested(client):
    """The benchmark starts later than the asset; both windows are shown."""
    headers = _auth_headers(client, "cmp-window@example.com")
    _seed_asset(client, headers, "EMBR3", ASSET_LEVELS)
    app.dependency_overrides[get_benchmark_provider] = lambda: FakeBenchmark(
        INDEX_LEVELS
    )
    client.post(
        f"{BENCHMARKS_URL}/IBOV/sync",
        json={"start": DAYS[2].isoformat(), "end": DAYS[-1].isoformat()},
        headers=headers,
    )

    body = client.get(
        f"{ASSETS_URL}/EMBR3/benchmarks/IBOV", params=_window(), headers=headers
    ).json()

    assert body["subject"]["start_date"] == DAYS[0].isoformat()
    assert body["benchmark"]["start_date"] == DAYS[2].isoformat()
