"""End-to-end tests for the portfolio scoring endpoint.

The whole chain — register, buy, sync prices, sync benchmarks, score —
with fake providers so nothing touches the network.

Dates are generated relative to today so the benchmark incomplete-period
rule never fires by accident on the day the suite runs.
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

DAYS = [datetime.now(UTC).date() - timedelta(days=60 - offset) for offset in range(6)]

#: A calm asset and a violent one, over the same window.
STEADY = ["100", "101", "102", "103", "104", "105"]
WILD = ["100", "130", "70", "120", "60", "105"]
INDEX = ["1000", "1010", "1020", "1030", "1040", "1050"]


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


def _seed_asset(client, headers, ticker, levels, sector=None):
    client.post(
        ASSETS_URL,
        json={
            "ticker": ticker,
            "name": ticker,
            "asset_type": "STOCK",
            **({"sector": sector} if sector else {}),
        },
        headers=headers,
    )
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketData(levels)
    client.post(f"{ASSETS_URL}/{ticker}/prices/sync", json=_window(), headers=headers)
    return client.get(f"{ASSETS_URL}/{ticker}", headers=headers).json()["id"]


def _seed_benchmarks(client, headers):
    app.dependency_overrides[get_benchmark_provider] = lambda: FakeBenchmark(INDEX)
    client.post(f"{BENCHMARKS_URL}/IBOV/sync", json=_window(), headers=headers)
    app.dependency_overrides[get_benchmark_provider] = lambda: FakeBenchmark(
        ["0.0005"] * len(DAYS)
    )
    client.post(f"{BENCHMARKS_URL}/CDI/sync", json=_window(), headers=headers)


def _portfolio(client, headers, name="Main"):
    return client.post(PORTFOLIOS_URL, json={"name": name}, headers=headers).json()[
        "id"
    ]


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


def _scores(client, headers, portfolio_id):
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/scores", params=_window(), headers=headers
    )
    assert response.status_code == 200
    return {entry["ticker"]: entry for entry in response.json()["scores"]}


# -- the shape of a score ---------------------------------------------


def test_scoring_requires_authentication(client):
    assert client.get(f"{PORTFOLIOS_URL}/1/scores").status_code == 401


def test_another_users_portfolio_cannot_be_scored(client):
    owner = _auth_headers(client, "sc-owner@example.com")
    portfolio_id = _portfolio(client, owner)

    intruder = _auth_headers(client, "sc-intruder@example.com")
    response = client.get(f"{PORTFOLIOS_URL}/{portfolio_id}/scores", headers=intruder)

    assert response.status_code == 404


def test_the_fundamentals_pillars_are_absent_rather_than_zero(client):
    """The project's actual state: no statements have been ingested.

    Quality, Valuation and Growth must come back `null` with their
    missing inputs named — not as a zero that would read as "bad company"
    and then disappear into the final score.
    """
    headers = _auth_headers(client, "sc-absent@example.com")
    _seed_asset(client, headers, "PETR4", STEADY)
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    entry = _scores(client, headers, portfolio_id)["PETR4"]
    pillars = {sub["name"]: sub for sub in entry["sub_scores"]}

    assert pillars["quality"]["value"] is None
    assert pillars["valuation"]["value"] is None
    assert pillars["growth"]["value"] is None
    assert set(pillars["quality"]["missing"]) == {"roe", "roic", "net_margin"}
    assert set(pillars["valuation"]["missing"]) == {"pe", "pb"}


def test_coverage_reports_that_the_score_rests_on_forty_percent(client):
    """Risk (0.25) and Diversification (0.15) of an intended 1.00.

    Without this number a caller would read a score of 70 as if the whole
    formula had been applied.
    """
    headers = _auth_headers(client, "sc-coverage@example.com")
    _seed_asset(client, headers, "VALE3", STEADY)
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    entry = _scores(client, headers, portfolio_id)["VALE3"]

    assert Decimal(entry["coverage"]) == Decimal("0.40")
    assert entry["final_score"] is not None


def test_the_risk_pillar_is_decomposable(client):
    """Rule 30: "why is this 62?" has to be answerable from the result."""
    headers = _auth_headers(client, "sc-decompose@example.com")
    _seed_asset(client, headers, "ITUB4", STEADY)
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    entry = _scores(client, headers, portfolio_id)["ITUB4"]
    risk = next(sub for sub in entry["sub_scores"] if sub["name"] == "risk")

    assert set(risk["components"]) == {
        "volatility",
        "max_drawdown",
        "beta",
        "sharpe",
    }
    assert risk["missing"] == []


def test_the_formula_version_is_reported(client):
    headers = _auth_headers(client, "sc-version@example.com")
    _seed_asset(client, headers, "BBAS3", STEADY)
    portfolio_id = _portfolio(client, headers)

    body = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/scores", params=_window(), headers=headers
    ).json()

    assert body["formula_version"] == body["scores"][0]["formula_version"]


# -- the numbers actually discriminate --------------------------------


def test_a_calm_asset_scores_better_on_risk_than_a_violent_one(client):
    headers = _auth_headers(client, "sc-risk@example.com")
    _seed_asset(client, headers, "STEADY3", STEADY)
    _seed_asset(client, headers, "WILD3", WILD)
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    scores = _scores(client, headers, portfolio_id)

    def risk_of(ticker):
        entry = scores[ticker]
        sub = next(s for s in entry["sub_scores"] if s["name"] == "risk")
        return Decimal(sub["value"])

    assert risk_of("STEADY3") > risk_of("WILD3")


def test_the_same_asset_scores_lower_once_the_portfolio_is_concentrated(client):
    """Rule 31: the question is which contribution improves *this* portfolio.

    An asset held at a heavy weight has less room left, so its
    Diversification pillar falls — the identical asset, the identical
    prices, a different portfolio.
    """
    headers = _auth_headers(client, "sc-concentration@example.com")
    asset_id = _seed_asset(client, headers, "WEGE3", STEADY)
    other_id = _seed_asset(client, headers, "RENT3", STEADY)
    _seed_benchmarks(client, headers)

    empty = _portfolio(client, headers, "Empty")
    concentrated = _portfolio(client, headers, "Concentrated")
    _buy(client, headers, concentrated, asset_id, 90, 100)
    _buy(client, headers, concentrated, other_id, 10, 100)

    def diversification(portfolio_id, ticker):
        entry = _scores(client, headers, portfolio_id)[ticker]
        sub = next(s for s in entry["sub_scores"] if s["name"] == "diversification")
        return Decimal(sub["value"])

    assert diversification(empty, "WEGE3") == Decimal(100)
    assert diversification(concentrated, "WEGE3") == Decimal(0)


def test_sector_concentration_is_counted_separately_from_asset_weight(client):
    """Two assets of the same sector concentrate it even when each is small."""
    headers = _auth_headers(client, "sc-sector@example.com")
    first = _seed_asset(client, headers, "BBDC4", STEADY, sector="Financeiro")
    second = _seed_asset(client, headers, "SANB11", STEADY, sector="Financeiro")
    _seed_benchmarks(client, headers)

    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, first, 15, 100)
    _buy(client, headers, portfolio_id, second, 15, 100)

    entry = _scores(client, headers, portfolio_id)["BBDC4"]
    sub = next(s for s in entry["sub_scores"] if s["name"] == "diversification")

    # Asset weight 50% is past its 20% ceiling; the sector is 100% of the
    # portfolio, past its 40% one. Both components floor at zero.
    assert sub["components"]["asset_weight"] == "0"
    assert sub["components"]["sector_weight"] == "0"


def test_an_asset_without_a_sector_is_scored_on_its_own_weight_alone(client):
    """Absent, not zero — an unknown sector is not an empty one."""
    headers = _auth_headers(client, "sc-nosector@example.com")
    _seed_asset(client, headers, "MGLU3", STEADY)
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    entry = _scores(client, headers, portfolio_id)["MGLU3"]
    sub = next(s for s in entry["sub_scores"] if s["name"] == "diversification")

    assert sub["missing"] == ["sector_weight"]


# -- ordering ----------------------------------------------------------


def test_scores_come_back_best_first_with_unscorable_assets_last(client):
    """An asset with no prices cannot be scored, and is still returned.

    Dropping it would make the gap invisible; the investor needs to see
    that it could not be evaluated.
    """
    headers = _auth_headers(client, "sc-order@example.com")
    _seed_asset(client, headers, "STEADY4", STEADY)
    _seed_asset(client, headers, "WILD4", WILD)
    client.post(
        ASSETS_URL,
        json={"ticker": "NODATA3", "name": "NODATA3", "asset_type": "STOCK"},
        headers=headers,
    )
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    body = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/scores", params=_window(), headers=headers
    ).json()
    tickers = [entry["ticker"] for entry in body["scores"]]

    assert tickers[-1] == "NODATA3"
    assert body["scores"][-1]["final_score"] is None
    assert tickers.index("STEADY4") < tickers.index("WILD4")


def test_an_asset_with_only_diversification_gets_no_final_score(client):
    """One pillar is not a composite (MIN_SUB_SCORES).

    NODATA3 has no prices, so Risk is absent too; Diversification alone
    remains, and a "Final Score" built on it would invite comparison with
    a five-pillar score.
    """
    headers = _auth_headers(client, "sc-single@example.com")
    client.post(
        ASSETS_URL,
        json={"ticker": "NOPRICE3", "name": "NOPRICE3", "asset_type": "STOCK"},
        headers=headers,
    )
    portfolio_id = _portfolio(client, headers)

    entry = _scores(client, headers, portfolio_id)["NOPRICE3"]

    assert entry["final_score"] is None
    assert Decimal(entry["coverage"]) == Decimal("0.15")


def test_scoring_never_calls_an_external_source(client):
    """Reading is a database operation (AGENTS.md rule 23)."""
    headers = _auth_headers(client, "sc-noio@example.com")
    _seed_asset(client, headers, "SUZB3", STEADY)
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    class Exploding(MarketDataProvider):
        def get_quote(self, ticker):  # pragma: no cover
            raise AssertionError("scoring must not call the source")

        def get_daily_history(self, ticker, start, end):  # pragma: no cover
            raise AssertionError("scoring must not call the source")

    app.dependency_overrides[get_market_data_provider] = lambda: Exploding()

    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/scores", params=_window(), headers=headers
    )

    assert response.status_code == 200
