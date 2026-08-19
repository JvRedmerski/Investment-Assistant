"""End-to-end tests for the contribution plan endpoint.

The whole chain — register, buy, sync prices, sync benchmarks, plan —
with fake providers so nothing touches the network.

The state these run against is the project's real one: no financial
statements have been ingested for these assets, so every score rests on
Risk and Diversification alone. That is why the first test below expects
an **empty** plan, and it is the honest end-to-end result rather than a
gap in the fixture.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.dependencies import get_benchmark_provider, get_market_data_provider
from app.domain.recommendations.allocation import MAX_ASSET_WEIGHT
from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.schemas import BenchmarkObservation
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.schemas import DailyBar
from app.main import app

ASSETS_URL = "/api/v1/assets"
BENCHMARKS_URL = "/api/v1/benchmarks"
PORTFOLIOS_URL = "/api/v1/portfolios"

DAYS = [datetime.now(UTC).date() - timedelta(days=60 - offset) for offset in range(6)]

STEADY = ["100", "101", "102", "103", "104", "105"]
WILD = ["100", "130", "70", "120", "60", "105"]
INDEX = ["1000", "1010", "1020", "1030", "1040", "1050"]

#: The universe here is scored on Risk and Diversification only, which is
#: 0.40 of the formula — under the default floor. Lowering it is what
#: rule 32 means by the limits being the investor's to set, and it is
#: what lets these tests exercise the allocation itself.
THIN_COVERAGE = "0.4"


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


def _seed_asset(client, headers, ticker, levels, sector="Energia"):
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


def _plan(client, headers, portfolio_id, **params):
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/contribution-plan",
        params={**_window_params(), **params},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _window_params():
    return {"start": DAYS[0].isoformat(), "as_of": DAYS[-1].isoformat()}


def _amounts(plan):
    return {item["ticker"]: Decimal(item["amount"]) for item in plan["allocations"]}


def _reasons(plan):
    return {item["ticker"]: item["reason"] for item in plan["skipped"]}


# -- access -----------------------------------------------------------


def test_the_plan_requires_authentication(client):
    assert client.get(f"{PORTFOLIOS_URL}/1/contribution-plan").status_code == 401


def test_another_users_portfolio_has_no_plan(client):
    owner = _auth_headers(client, "cp-owner@example.com")
    portfolio_id = _portfolio(client, owner)

    intruder = _auth_headers(client, "cp-intruder@example.com")
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/contribution-plan", headers=intruder
    )

    assert response.status_code == 404


# -- the state the project is actually in ------------------------------


def test_without_statements_the_whole_universe_is_under_the_coverage_floor(client):
    """Not a fixture gap — the honest end-to-end answer today.

    With no filings ingested, every score rests on Risk and
    Diversification: 0.40 of the formula, under the 0.50 floor. Rather
    than pay out on scores that are mostly a description of what is
    missing, the plan funds nothing and names the reason for every asset.
    """
    headers = _auth_headers(client, "cp-floor@example.com")
    _seed_asset(client, headers, "PETR4", STEADY)
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    plan = _plan(client, headers, portfolio_id)

    assert plan["allocations"] == []
    assert Decimal(plan["unallocated"]) == Decimal("1000.00")
    assert _reasons(plan) == {"PETR4": "COVERAGE_BELOW_MINIMUM"}
    assert "40.0%" in plan["skipped"][0]["detail"]


def test_the_contribution_defaults_to_a_thousand_reais(client):
    """Rule 33's starting value, for an account with no profile yet."""
    headers = _auth_headers(client, "cp-default@example.com")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    plan = _plan(client, headers, portfolio_id)

    assert Decimal(plan["contribution"]) == Decimal("1000.00")


def test_a_custom_amount_is_honoured(client):
    headers = _auth_headers(client, "cp-amount@example.com")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    plan = _plan(client, headers, portfolio_id, amount="250.50")

    assert Decimal(plan["contribution"]) == Decimal("250.50")
    assert Decimal(plan["unallocated"]) == Decimal("250.50")


# -- an actual plan ----------------------------------------------------


def test_the_first_contribution_is_capped_at_the_asset_ceiling(client):
    """An empty portfolio: the base is the contribution itself.

    So the 20% ceiling is R$ 200 per name, and with two assets tracked
    R$ 600 of the R$ 1.000 has nowhere to go. Reported, not forced.
    """
    headers = _auth_headers(client, "cp-first@example.com")
    _seed_asset(client, headers, "STDY3", STEADY, sector="Energia")
    _seed_asset(client, headers, "WILD3", WILD, sector="Bancos")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    plan = _plan(client, headers, portfolio_id, min_coverage=THIN_COVERAGE)

    assert _amounts(plan) == {"STDY3": Decimal("200.00"), "WILD3": Decimal("200.00")}
    assert all(item["limited_by"] == "ASSET_WEIGHT" for item in plan["allocations"])
    assert Decimal(plan["unallocated"]) == Decimal("600.00")


def test_the_calmer_asset_is_funded_first(client):
    """Risk is a quarter of the score, calibrated for a conservative.

    Nothing in the allocator re-tests volatility; the ranking inherits it
    from the score, which is the point of combining rather than
    recalculating.
    """
    headers = _auth_headers(client, "cp-rank@example.com")
    _seed_asset(client, headers, "STDY3", STEADY, sector="Energia")
    _seed_asset(client, headers, "WILD3", WILD, sector="Bancos")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    plan = _plan(client, headers, portfolio_id, min_coverage=THIN_COVERAGE)

    assert [item["ticker"] for item in plan["allocations"]] == ["STDY3", "WILD3"]
    assert plan["allocations"][0]["rank"] == 1


def test_an_asset_already_at_its_ceiling_is_passed_over(client):
    """Rule 31: the question is which contribution improves *this* portfolio.

    R$ 5.000 already in STDY3 is 20% of the R$ 25.000 the portfolio will
    hold after the contribution, so it is full — even though it is the
    better-scoring of the two.
    """
    headers = _auth_headers(client, "cp-full@example.com")
    steady_id = _seed_asset(client, headers, "STDY3", STEADY, sector="Energia")
    _seed_asset(client, headers, "WILD3", WILD, sector="Bancos")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, steady_id, quantity=200, price=100)

    plan = _plan(client, headers, portfolio_id, min_coverage=THIN_COVERAGE)

    assert _reasons(plan)["STDY3"] == "ASSET_LIMIT_REACHED"
    assert set(_amounts(plan)) == {"WILD3"}


def test_the_weights_reported_are_the_ones_the_investor_will_have(client):
    headers = _auth_headers(client, "cp-weights@example.com")
    _seed_asset(client, headers, "STDY3", STEADY, sector="Energia")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    plan = _plan(client, headers, portfolio_id, min_coverage=THIN_COVERAGE)

    (allocation,) = plan["allocations"]
    assert Decimal(plan["base_value"]) == Decimal("1000.00")
    assert Decimal(allocation["weight_before"]) == Decimal(0)
    assert Decimal(allocation["weight_after"]) == MAX_ASSET_WEIGHT


# -- the policy is the investor's (rule 32) ----------------------------


def test_every_limit_is_overridable_and_echoed_back(client):
    headers = _auth_headers(client, "cp-policy@example.com")
    _seed_asset(client, headers, "STDY3", STEADY, sector="Energia")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    plan = _plan(
        client,
        headers,
        portfolio_id,
        min_coverage=THIN_COVERAGE,
        max_asset_weight="0.5",
        max_sector_weight="0.6",
        max_positions=1,
        min_score="10",
    )

    assert Decimal(plan["policy"]["max_asset_weight"]) == Decimal("0.5")
    assert Decimal(plan["policy"]["max_sector_weight"]) == Decimal("0.6")
    assert plan["policy"]["max_positions"] == 1
    assert Decimal(plan["policy"]["min_score"]) == Decimal(10)
    # Both ceilings are now looser than the per-position share on a
    # R$ 1.000 base (R$ 500 and R$ 600 against R$ 400), so the share is
    # what decides, and the response says which.
    assert _amounts(plan) == {"STDY3": Decimal("400.00")}
    assert plan["allocations"][0]["limited_by"] == "POSITION_SHARE"


def test_an_asset_with_no_sector_is_refused_until_the_rule_is_relaxed(client):
    """A sector ceiling that cannot be evaluated is not a ceiling."""
    headers = _auth_headers(client, "cp-sector@example.com")
    _seed_asset(client, headers, "NOSEC3", STEADY, sector=None)
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    strict = _plan(client, headers, portfolio_id, min_coverage=THIN_COVERAGE)
    relaxed = _plan(
        client,
        headers,
        portfolio_id,
        min_coverage=THIN_COVERAGE,
        require_sector="false",
    )

    assert _reasons(strict) == {"NOSEC3": "SECTOR_UNKNOWN"}
    assert set(_amounts(relaxed)) == {"NOSEC3"}


# -- the plan explains itself ------------------------------------------


def test_each_allocation_carries_the_pillars_behind_it(client):
    """Decomposable the way the score is (rule 30).

    "Why this asset?" is answerable from the response alone, down to the
    individual metrics, without calling the scores endpoint too.
    """
    headers = _auth_headers(client, "cp-explain@example.com")
    _seed_asset(client, headers, "STDY3", STEADY, sector="Energia")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    plan = _plan(client, headers, portfolio_id, min_coverage=THIN_COVERAGE)

    (allocation,) = plan["allocations"]
    pillars = {sub["name"]: sub for sub in allocation["sub_scores"]}
    assert pillars["risk"]["value"] is not None
    assert set(pillars["risk"]["components"]) == {
        "volatility",
        "max_drawdown",
        "beta",
        "sharpe",
    }
    assert pillars["quality"]["value"] is None
    assert Decimal(allocation["coverage"]) == Decimal("0.40")
    assert plan["rules_version"] and plan["formula_version"]


def test_the_same_request_twice_gives_the_same_plan(client):
    """Rule 113. Nothing is stored, so this is the only guarantee there is."""
    headers = _auth_headers(client, "cp-deterministic@example.com")
    _seed_asset(client, headers, "STDY3", STEADY, sector="Energia")
    _seed_asset(client, headers, "WILD3", WILD, sector="Bancos")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)

    first = _plan(client, headers, portfolio_id, min_coverage=THIN_COVERAGE)
    second = _plan(client, headers, portfolio_id, min_coverage=THIN_COVERAGE)

    assert first == second
