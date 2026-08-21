"""End-to-end tests for the backtesting endpoint (W13-006).

The whole chain — register, track an asset, sync its prices, run a
backtest — with a fake provider so nothing touches the network.

The universe these run against carries no financial statements, so every
score rests on Risk and Diversification alone: 0,40 of the formula, under
the default floor. That is why `min_coverage` is lowered here, exactly as
`test_contribution_plan_routes` does — it is what rule 32 means by the
limits being the investor's to set.
"""

from datetime import date, timedelta
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
BACKTESTS_URL = "/api/v1/backtests"

#: Two years of consecutive sessions, so a monthly contribution has
#: somewhere to land more than once.
DAYS = [date(2024, 1, 1) + timedelta(days=offset) for offset in range(400)]

#: Coverage without a single financial statement is 0,40.
THIN_COVERAGE = "0.4"


class FakeMarketData(MarketDataProvider):
    def __init__(self, close: str = "10"):
        price = Decimal(close)
        self._bars = [
            DailyBar(
                date=day,
                open=price,
                high=price,
                low=price,
                close=price,
                adjusted_close=price,
                volume=Decimal(1000),
            )
            for day in DAYS
        ]

    def get_quote(self, ticker):  # pragma: no cover - unused here
        raise NotImplementedError

    def get_daily_history(self, ticker, start, end):
        return [bar for bar in self._bars if start <= bar.date <= end]


class FakeBenchmark(BenchmarkProvider):
    def __init__(self, value: str):
        self._observations = [
            BenchmarkObservation(date=day, value=Decimal(value)) for day in DAYS
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


def _auth_headers(client, email="backtest@example.com"):
    client.post(
        "/api/v1/auth/register", json={"email": email, "password": "SuperSecret123"}
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _window():
    return {"start": DAYS[0].isoformat(), "end": DAYS[-1].isoformat()}


def _seed_asset(client, headers, ticker="AAA3", sector="Energia"):
    client.post(
        ASSETS_URL,
        json={
            "ticker": ticker,
            "name": ticker,
            "asset_type": "STOCK",
            "sector": sector,
        },
        headers=headers,
    )
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketData()
    client.post(f"{ASSETS_URL}/{ticker}/prices/sync", json=_window(), headers=headers)


def _run(client, headers, **params):
    return client.get(
        BACKTESTS_URL,
        params={
            "start": DAYS[0].isoformat(),
            "end": DAYS[-1].isoformat(),
            "min_coverage": THIN_COVERAGE,
            **params,
        },
        headers=headers,
    )


# -- the happy path ---------------------------------------------------


def test_a_backtest_reports_the_two_curves_and_the_trades(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    response = _run(client, headers, day_of_month=5)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["universe"] == ["AAA3"]
    assert body["excluded"] == []
    assert body["wealth"]
    assert body["index"]
    assert body["trades"]["buys"] > 0


def test_the_settings_come_back_with_the_result(client):
    """Rule 113: a figure that cannot say what produced it is not
    reproducible."""
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    body = _run(client, headers, amount="500").json()

    assert body["settings"]["contribution"] == "500"
    assert body["settings"]["strategy"] == "contribution-plan"
    assert body["settings"]["publication_lag_months"] == 3
    assert body["settings"]["costs"]["exchange_rate"] == "0.0003"
    assert body["settings"]["policy"]["min_coverage"] == "0.4"


def test_costs_are_charged_unless_they_are_explicitly_waived(client):
    """Rule 107: a backtest without costs is not a final result, so zero
    has to be asked for."""
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    charged = _run(client, headers).json()
    waived = _run(client, headers, exchange_rate="0").json()

    assert Decimal(charged["trades"]["fees"]) > 0
    assert Decimal(waived["trades"]["fees"]) == 0


def test_the_money_curve_carries_the_contribution_line_under_it(client):
    """ADR-019: patrimonial growth must not be readable as performance."""
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    body = _run(client, headers, amount="1000", day_of_month=5).json()

    final = body["wealth"][-1]
    assert Decimal(final["contributed"]) > 0
    assert Decimal(final["holdings"]) + Decimal(final["cash"]) == Decimal(
        final["total"]
    )


def test_every_figure_defined_on_a_closed_trade_is_absent(client):
    """Nothing this project ships sells, so nothing ever closes."""
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    trades = _run(client, headers).json()["trades"]

    assert trades["sells"] == 0
    assert trades["closed_trades"] == 0
    assert trades["win_rate"] is None
    assert trades["expectancy"] is None
    assert trades["profit_factor"] is None


def test_the_rebalancing_plan_can_be_replayed_too(client):
    """And on this universe it correctly funds nothing.

    A target comes from **merit** — Quality, Valuation, Growth and Risk
    without the pillar that reads the portfolio (ADR-027) — and merit
    needs at least two of those four, since a composite of one is that
    one under another name. No statement has been ingested here, so only
    Risk exists and every asset is excluded with `NO_MERIT_SCORE`.

    The honest end-to-end result rather than a gap in the fixture: the
    contribution plan can rank on a thinner base than the drift table
    can, and a run that bought anyway would be the bug.
    `test_backtest_service` covers the funded case, where statements
    exist.
    """
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    body = _run(client, headers, strategy="rebalance-plan").json()

    assert body["settings"]["strategy"] == "rebalance-plan"
    assert body["trades"]["buys"] == 0
    assert body["universe"] == ["AAA3"]


def test_a_benchmark_is_measured_when_one_is_asked_for(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)
    app.dependency_overrides[get_benchmark_provider] = lambda: FakeBenchmark("1000")
    client.post(f"{BENCHMARKS_URL}/IBOV/sync", json=_window(), headers=headers)

    body = _run(client, headers, benchmark="IBOV").json()

    assert body["comparison"] is not None
    assert body["comparison"]["benchmark_code"] == "IBOV"


# -- what it refuses --------------------------------------------------


def test_a_backtest_requires_authentication(client):
    response = client.get(BACKTESTS_URL, params={"start": DAYS[0].isoformat()})

    assert response.status_code == 401


def test_an_unknown_strategy_is_named_rather_than_guessed_at(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    response = _run(client, headers, strategy="momentum")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNKNOWN_STRATEGY"


def test_a_window_that_ends_before_it_starts_is_refused(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    response = client.get(
        BACKTESTS_URL,
        params={"start": DAYS[-1].isoformat(), "end": DAYS[0].isoformat()},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_WINDOW"


def test_an_unknown_benchmark_is_a_404_naming_it(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    response = _run(client, headers, benchmark="NASDAQ")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BENCHMARK_NOT_FOUND"


def test_an_empty_universe_says_what_to_do_about_it(client):
    headers = _auth_headers(client)

    response = _run(client, headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EMPTY_UNIVERSE"


def test_an_asset_with_no_prices_is_excluded_by_name(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)
    client.post(
        ASSETS_URL,
        json={
            "ticker": "BBB3",
            "name": "BBB3",
            "asset_type": "STOCK",
            "sector": "Financeiro",
        },
        headers=headers,
    )

    body = _run(client, headers).json()

    assert body["universe"] == ["AAA3"]
    assert body["excluded"] == [{"ticker": "BBB3", "reason": "NO_PRICES"}]


def test_nothing_is_written_by_running_one(client):
    """Rule 16: a backtest is derived, so it leaves no transaction behind."""
    headers = _auth_headers(client)
    _seed_asset(client, headers)
    portfolio_id = client.post(
        "/api/v1/portfolios", json={"name": "Main"}, headers=headers
    ).json()["id"]

    _run(client, headers)

    transactions = client.get(
        f"/api/v1/portfolios/{portfolio_id}/transactions", headers=headers
    )
    assert transactions.json() == []


def test_the_same_request_twice_produces_the_same_run(client):
    """Rule 113, over the endpoint and not only the engine."""
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    first = _run(client, headers, day_of_month=5).json()
    second = _run(client, headers, day_of_month=5).json()

    assert first["wealth"] == second["wealth"]
    assert first["trades"] == second["trades"]
