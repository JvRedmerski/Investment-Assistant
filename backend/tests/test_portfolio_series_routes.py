"""End-to-end tests for the evolution-chart endpoint.

The whole chain — register, sync prices and a benchmark, buy, read the
series — with fake providers so nothing touches the network.
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

DAYS = [datetime.now(UTC).date() - timedelta(days=10 - offset) for offset in range(4)]

#: 10 -> 11 -> 12 -> 12: a 20% rise then a flat day.
CLOSES = ["10", "11", "12", "12"]


class FakeMarketData(MarketDataProvider):
    #: Stored on every bar this provider supplies, and reported back by
    #: the series endpoint as its `sources` — rule 74 asks a chart to be
    #: able to say where its numbers came from.
    source_name = "brapi"

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
            for day, close in zip(DAYS, closes)
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


def _portfolio(client, headers):
    return client.post(PORTFOLIOS_URL, json={"name": "Main"}, headers=headers).json()[
        "id"
    ]


def _seed_asset(client, headers, ticker="PETR4", closes=None):
    client.post(
        ASSETS_URL,
        json={"ticker": ticker, "name": ticker, "asset_type": "STOCK"},
        headers=headers,
    )
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketData(
        closes or CLOSES
    )
    client.post(f"{ASSETS_URL}/{ticker}/prices/sync", json=_window(), headers=headers)
    return client.get(f"{ASSETS_URL}/{ticker}", headers=headers).json()["id"]


def _seed_cdi(client, headers, daily_rate="0.0005"):
    app.dependency_overrides[get_benchmark_provider] = lambda: FakeBenchmark(
        [daily_rate] * len(DAYS)
    )
    client.post(f"{BENCHMARKS_URL}/CDI/sync", json=_window(), headers=headers)


def _buy(client, headers, portfolio_id, asset_id, quantity, price, day=0):
    client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": str(quantity),
            "price": str(price),
            "transaction_date": datetime.combine(
                DAYS[day], datetime.min.time()
            ).isoformat(),
        },
        headers=headers,
    )


def _series(client, headers, portfolio_id, **params):
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/series",
        params={**_window_params(), **params},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _window_params():
    return {"start": DAYS[0].isoformat(), "end": DAYS[-1].isoformat()}


# -- access ------------------------------------------------------------


def test_the_series_requires_authentication(client):
    assert client.get(f"{PORTFOLIOS_URL}/1/series").status_code == 401


def test_another_users_portfolio_has_no_series(client):
    owner = _auth_headers(client, "ps-owner@example.com")
    portfolio_id = _portfolio(client, owner)

    intruder = _auth_headers(client, "ps-intruder@example.com")
    response = client.get(f"{PORTFOLIOS_URL}/{portfolio_id}/series", headers=intruder)

    assert response.status_code == 404


def test_an_unknown_benchmark_is_refused_by_name(client):
    headers = _auth_headers(client, "ps-unknown@example.com")
    portfolio_id = _portfolio(client, headers)

    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/series",
        params={"benchmark": "NOPE"},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BENCHMARK_NOT_FOUND"


# -- the two curves ----------------------------------------------------


@pytest.fixture
def held(client):
    """100 shares bought on the first day, price 10 -> 12."""
    headers = _auth_headers(client, "ps-held@example.com")
    asset_id = _seed_asset(client, headers)
    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, asset_id, 100, "10")
    return headers, portfolio_id


def test_the_wealth_curve_is_holdings_at_the_raw_close(held, client):
    headers, portfolio_id = held

    data = _series(client, headers, portfolio_id)

    assert [Decimal(point["value"]) for point in data["wealth"]] == [
        Decimal(1000),
        Decimal(1100),
        Decimal(1200),
        Decimal(1200),
    ]
    # Nothing was added after the first day, so the cost line is flat.
    assert {Decimal(point["invested"]) for point in data["wealth"]} == {Decimal(1000)}


def test_the_index_starts_at_the_base_and_tracks_the_return(held, client):
    headers, portfolio_id = held

    data = _series(client, headers, portfolio_id)

    assert Decimal(data["base"]) == 100
    assert [Decimal(point["value"]) for point in data["index"]] == [
        Decimal(100),
        Decimal(110),
        Decimal(120),
        Decimal(120),
    ]


def test_the_chart_can_state_what_it_is_showing(held, client):
    """Rule 74: período, unidade, benchmark, moeda, fonte, atualização."""
    headers, portfolio_id = held

    data = _series(client, headers, portfolio_id)

    assert data["currency"] == "BRL"
    assert data["base_date"] == DAYS[0].isoformat()
    assert data["end_date"] == DAYS[-1].isoformat()
    assert data["sources"] == ["brapi"]
    assert data["generated_at"]
    assert data["benchmark_code"] is None


def test_a_contribution_lifts_both_lines_but_only_one_return(client):
    """The reading the two lines exist to prevent.

    Buying again on the last day doubles the wealth curve without the
    index moving: money arriving is not performance (ADR-019).
    """
    headers = _auth_headers(client, "ps-flow@example.com")
    asset_id = _seed_asset(client, headers, closes=["10", "10", "10", "10"])
    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, asset_id, 100, "10", day=0)
    _buy(client, headers, portfolio_id, asset_id, 100, "10", day=3)

    data = _series(client, headers, portfolio_id)

    wealth = [Decimal(point["value"]) for point in data["wealth"]]
    assert wealth[0] == Decimal(1000)
    assert wealth[-1] == Decimal(2000)
    assert {Decimal(point["value"]) for point in data["index"]} == {Decimal(100)}


# -- against a benchmark -----------------------------------------------


def test_the_benchmark_is_rebased_onto_the_same_start(held, client):
    headers, portfolio_id = held
    _seed_cdi(client, headers)

    data = _series(client, headers, portfolio_id, benchmark="CDI")

    assert data["benchmark_code"] == "CDI"
    assert data["benchmark_name"]
    assert Decimal(data["benchmark_index"][0]["value"]) == 100
    assert Decimal(data["index"][0]["value"]) == 100
    # 0.05% a day compounded is a long way behind a 20% rise.
    assert Decimal(data["benchmark_index"][-1]["value"]) < Decimal(101)
    assert data["benchmark"]["observations"] == len(DAYS)


def test_both_summaries_come_back(held, client):
    headers, portfolio_id = held
    _seed_cdi(client, headers)

    data = _series(client, headers, portfolio_id, benchmark="CDI")

    assert Decimal(data["subject"]["total_return"]) == Decimal("0.2")
    assert data["subject"]["observations"] == len(DAYS)


# -- nothing to draw ---------------------------------------------------


def test_an_empty_portfolio_has_no_curves(client):
    headers = _auth_headers(client, "ps-empty@example.com")
    portfolio_id = _portfolio(client, headers)

    data = _series(client, headers, portfolio_id)

    assert data["wealth"] == []
    assert data["index"] == []
    assert data["base_date"] is None
    assert data["sources"] == []
