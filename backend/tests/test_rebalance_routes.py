"""End-to-end tests for the drift table endpoint (AGENTS.md rule 34).

The whole chain — register, seed statements, sync prices and benchmarks,
buy, read the table — with fake providers so nothing touches the network.

Two of these assert an **empty** answer, and neither is a fixture gap.
A target needs at least two of Quality, Valuation, Growth and Risk, and
an asset with no filings has only Risk however low the coverage floor is
set. That is the honest end-to-end result and it is the state most of
this project's real universe is in.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.dependencies import (
    get_benchmark_provider,
    get_fundamentals_provider,
    get_market_data_provider,
)
from app.domain.recommendations.allocation import MAX_ASSET_WEIGHT
from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.schemas import BenchmarkObservation
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.schemas import FinancialStatement
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.schemas import DailyBar
from app.main import app

ASSETS_URL = "/api/v1/assets"
BENCHMARKS_URL = "/api/v1/benchmarks"
PORTFOLIOS_URL = "/api/v1/portfolios"

DAYS = [datetime.now(UTC).date() - timedelta(days=60 - offset) for offset in range(6)]

STEADY = ["100", "101", "102", "103", "104", "105"]
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


class FakeFundamentals(FundamentalsProvider):
    def __init__(self, statements):
        self._statements = statements

    def get_annual_statements(self, ticker):
        return list(self._statements)

    def close(self):
        pass


def _statement(year: int, revenue: str, net_income: str) -> FinancialStatement:
    return FinancialStatement(
        reference_date=date(year, 12, 31),
        revenue=Decimal(revenue),
        net_income=Decimal(net_income),
        equity=Decimal(600),
        debt=Decimal(400),
        cash=Decimal(100),
    )


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    for dependency in (
        get_benchmark_provider,
        get_fundamentals_provider,
        get_market_data_provider,
    ):
        app.dependency_overrides.pop(dependency, None)


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


def _window_params():
    return {"start": DAYS[0].isoformat(), "as_of": DAYS[-1].isoformat()}


def _seed_asset(client, headers, ticker, sector="Energia", statements=True):
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
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketData(STEADY)
    client.post(f"{ASSETS_URL}/{ticker}/prices/sync", json=_window(), headers=headers)

    if statements:
        app.dependency_overrides[get_fundamentals_provider] = lambda: FakeFundamentals(
            [_statement(2023, "800", "120"), _statement(2024, "1000", "150")]
        )
        client.post(f"{ASSETS_URL}/{ticker}/fundamentals/sync", headers=headers)
        client.post(f"{ASSETS_URL}/{ticker}/indicators/compute", headers=headers)

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


def _buy(client, headers, portfolio_id, asset_id, quantity, price):
    client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "BUY",
            "quantity": str(quantity),
            "price": str(price),
            "transaction_date": datetime.combine(
                DAYS[0], datetime.min.time()
            ).isoformat(),
        },
        headers=headers,
    )


def _rebalance(client, headers, portfolio_id, **params):
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/rebalance",
        params={**_window_params(), **params},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _rows(table):
    return {row["ticker"]: row for row in table["targets"]}


# -- access -----------------------------------------------------------


def test_the_table_requires_authentication(client):
    assert client.get(f"{PORTFOLIOS_URL}/1/rebalance").status_code == 401


def test_another_users_portfolio_has_no_table(client):
    owner = _auth_headers(client, "rb-owner@example.com")
    portfolio_id = _portfolio(client, owner)

    intruder = _auth_headers(client, "rb-intruder@example.com")
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/rebalance", headers=intruder
    )

    assert response.status_code == 404


# -- what an asset with no filings gets --------------------------------


def test_without_statements_nothing_has_a_target(client):
    """Risk alone is one merit pillar, and one pillar is not a composite."""
    headers = _auth_headers(client, "rb-nofilings@example.com")
    _seed_benchmarks(client, headers)
    _seed_asset(client, headers, "AAAA3", statements=False)
    portfolio_id = _portfolio(client, headers)

    table = _rebalance(client, headers, portfolio_id)

    row = _rows(table)["AAAA3"]
    assert row["excluded"] == "NO_MERIT_SCORE"
    assert row["merit_score"] is None
    assert Decimal(row["target_weight"]) == 0
    # It still has a final score — Diversification is the second pillar.
    assert row["final_score"] is not None
    assert Decimal(table["unassigned"]) == 1


def test_lowering_the_coverage_floor_does_not_conjure_a_target(client):
    """The floor is not what is missing; a second merit pillar is.

    The contribution plan can be opened up this way, because its
    coverage test is the only thing standing between it and a score.
    A target needs merit to exist at all, and no policy knob creates a
    pillar that was never computed.
    """
    headers = _auth_headers(client, "rb-floor@example.com")
    _seed_benchmarks(client, headers)
    _seed_asset(client, headers, "AAAA3", statements=False)
    portfolio_id = _portfolio(client, headers)

    table = _rebalance(client, headers, portfolio_id, min_coverage="0.01")

    assert _rows(table)["AAAA3"]["excluded"] == "NO_MERIT_SCORE"


# -- the table proper --------------------------------------------------


@pytest.fixture
def seeded(client):
    """One rated asset and one unrated one, both held."""
    headers = _auth_headers(client, "rb-table@example.com")
    _seed_benchmarks(client, headers)
    rated = _seed_asset(client, headers, "AAAA3")
    unrated = _seed_asset(client, headers, "BBBB3", statements=False)
    portfolio_id = _portfolio(client, headers)
    # R$ 200 of the rated name and R$ 800 of the unrated one.
    _buy(client, headers, portfolio_id, rated, "2", "100")
    _buy(client, headers, portfolio_id, unrated, "8", "100")
    return headers, portfolio_id


def test_a_rated_asset_is_capped_by_the_per_asset_ceiling(seeded, client):
    """One rateable name cannot be handed the whole portfolio.

    Its merit is the only merit in the universe, so its proportional
    share is all of it; the 20% ceiling is what it actually gets, and
    the other 80% is reported as belonging to nobody rather than
    quietly given to the only name that could be scored.
    """
    headers, portfolio_id = seeded

    table = _rebalance(client, headers, portfolio_id)

    row = _rows(table)["AAAA3"]
    assert Decimal(row["target_weight"]) == MAX_ASSET_WEIGHT
    assert row["limited_by"] == "ASSET_WEIGHT"
    assert row["merit_score"] is not None
    assert Decimal(table["assigned"]) == MAX_ASSET_WEIGHT
    assert Decimal(table["unassigned"]) == 1 - MAX_ASSET_WEIGHT


def test_the_gap_is_the_target_minus_what_is_held(seeded, client):
    """Rule 34's three numbers, on a R$ 1.000 portfolio.

    R$ 200 of AAAA3 is 20% against a 20% target: on target, gap zero.
    R$ 800 of BBBB3 is 80% against no target at all.
    """
    headers, portfolio_id = seeded

    table = _rebalance(client, headers, portfolio_id)
    rows = _rows(table)

    assert Decimal(rows["AAAA3"]["current_weight"]) == Decimal("0.200000")
    assert Decimal(rows["AAAA3"]["weight_gap"]) == 0
    assert rows["AAAA3"]["status"] == "ON_TARGET"

    assert Decimal(rows["BBBB3"]["current_weight"]) == Decimal("0.800000")
    assert Decimal(rows["BBBB3"]["weight_gap"]) == Decimal("-0.800000")
    assert rows["BBBB3"]["status"] == "OVER"
    assert Decimal(table["overweight_gap"]) == Decimal("0.800000")


def test_a_held_asset_with_no_target_still_has_a_row(seeded, client):
    """The row that must not go missing: 80% of the portfolio.

    Dropping unrateable assets would leave a table that explains a fifth
    of the money and says nothing about the rest.
    """
    headers, portfolio_id = seeded

    rows = _rows(_rebalance(client, headers, portfolio_id))

    assert rows["BBBB3"]["excluded"] == "NO_MERIT_SCORE"
    assert rows["BBBB3"]["limited_by"] is None
    assert "fewer than two" in rows["BBBB3"]["detail"]


def test_rows_come_back_most_underweight_first(seeded, client):
    """Rule 34's priority order: 0.0 p.p. before -80 p.p."""
    headers, portfolio_id = seeded

    table = _rebalance(client, headers, portfolio_id)

    assert [row["ticker"] for row in table["targets"]] == ["AAAA3", "BBBB3"]


def test_the_band_is_the_investors_to_set(seeded, client):
    """Rule 32: every limit is configurable, this one included."""
    headers, portfolio_id = seeded

    # AAAA3 sits exactly on its target, so no band makes it drift.
    default = _rows(_rebalance(client, headers, portfolio_id))
    assert default["AAAA3"]["status"] == "ON_TARGET"

    # Cutting the per-asset ceiling to 15% moves the target under what
    # is held: 20% against 15% is 5 p.p. over, inside a 10 p.p. band.
    tight = _rows(_rebalance(client, headers, portfolio_id, max_asset_weight="0.15"))
    assert Decimal(tight["AAAA3"]["target_weight"]) == Decimal("0.150000")
    assert tight["AAAA3"]["status"] == "OVER"

    wide = _rows(
        _rebalance(
            client,
            headers,
            portfolio_id,
            max_asset_weight="0.15",
            rebalance_band="0.10",
        )
    )
    assert wide["AAAA3"]["status"] == "ON_TARGET"


def test_the_policy_is_echoed_back(seeded, client):
    headers, portfolio_id = seeded

    table = _rebalance(client, headers, portfolio_id, min_score="60")

    assert Decimal(table["policy"]["min_score"]) == 60
    # Untouched limits keep their conservative defaults.
    assert Decimal(table["policy"]["max_asset_weight"]) == MAX_ASSET_WEIGHT
    assert Decimal(table["policy"]["rebalance_band"]) == Decimal("0.02")


def test_the_table_records_the_versions_it_was_built_from(seeded, client):
    """Rule 30: traceable to both the scores and the target model."""
    headers, portfolio_id = seeded

    table = _rebalance(client, headers, portfolio_id)

    assert table["model_version"]
    assert table["formula_version"]


def test_an_empty_portfolio_is_entirely_underweight(client):
    """Where every portfolio starts, and the answer has to be usable."""
    headers = _auth_headers(client, "rb-empty@example.com")
    _seed_benchmarks(client, headers)
    _seed_asset(client, headers, "AAAA3")
    portfolio_id = _portfolio(client, headers)

    table = _rebalance(client, headers, portfolio_id)

    row = _rows(table)["AAAA3"]
    assert Decimal(table["invested"]) == 0
    assert Decimal(row["current_weight"]) == 0
    assert Decimal(row["weight_gap"]) == MAX_ASSET_WEIGHT
    assert row["status"] == "UNDER"
    assert Decimal(table["untracked_weight"]) == 0


# -- the plan that closes the gaps -------------------------------------


def _plan(client, headers, portfolio_id, **params):
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/rebalance-plan",
        params={**_window_params(), **params},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _placed(plan):
    return {item["ticker"]: Decimal(item["amount"]) for item in plan["allocations"]}


def _skipped(plan):
    return {item["ticker"]: item["reason"] for item in plan["skipped"]}


def test_the_plan_requires_authentication(client):
    assert client.get(f"{PORTFOLIOS_URL}/1/rebalance-plan").status_code == 401


def test_another_users_portfolio_has_no_plan(client):
    owner = _auth_headers(client, "rp-owner@example.com")
    portfolio_id = _portfolio(client, owner)

    intruder = _auth_headers(client, "rp-intruder@example.com")
    response = client.get(
        f"{PORTFOLIOS_URL}/{portfolio_id}/rebalance-plan", headers=intruder
    )

    assert response.status_code == 404


@pytest.fixture
def underweight(client):
    """R$ 100 in a rated name and R$ 900 in an unrated one."""
    headers = _auth_headers(client, "rp-plan@example.com")
    _seed_benchmarks(client, headers)
    rated = _seed_asset(client, headers, "AAAA3", sector="Energia")
    unrated = _seed_asset(client, headers, "BBBB3", sector="Bancos", statements=False)
    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, rated, "1", "100")
    _buy(client, headers, portfolio_id, unrated, "9", "100")
    return headers, portfolio_id


def test_the_plan_funds_the_gap_up_to_the_target(underweight, client):
    """R$ 1.000 arriving on a R$ 1.000 portfolio makes the base R$ 2.000.

    AAAA3 targets 20% of that — R$ 400 — and already holds R$ 100, so
    R$ 300 closes it exactly. The remaining R$ 700 has nowhere to go:
    the only other name in the universe has no target at all.
    """
    headers, portfolio_id = underweight

    plan = _plan(client, headers, portfolio_id)

    assert Decimal(plan["base_value"]) == 2000
    assert _placed(plan) == {"AAAA3": Decimal("300.00")}
    line = plan["allocations"][0]
    assert line["limited_by"] == "TARGET_WEIGHT"
    assert Decimal(line["needed"]) == Decimal("300.00")
    assert Decimal(line["weight_gap"]) == Decimal("0.100000")
    assert Decimal(line["weight_after"]) == Decimal("0.20")
    assert Decimal(line["gap_after"]) == 0
    assert Decimal(plan["allocated"]) + Decimal(plan["unallocated"]) == Decimal(
        plan["contribution"]
    )


def test_the_plan_never_sells_what_it_cannot_rate(underweight, client):
    """90% of the portfolio has no target, and the answer is not "sell"."""
    headers, portfolio_id = underweight

    plan = _plan(client, headers, portfolio_id)

    assert _skipped(plan)["BBBB3"] == "NO_MERIT_SCORE"
    assert all(Decimal(item["amount"]) > 0 for item in plan["allocations"])


def test_the_distance_left_is_reported_alongside_the_distance_before(
    underweight, client
):
    """Rule 30: the plan says what it achieved, not only what it did."""
    headers, portfolio_id = underweight

    plan = _plan(client, headers, portfolio_id)

    assert Decimal(plan["underweight_before"]) == Decimal("0.100000")
    assert Decimal(plan["underweight_after"]) == 0


def test_a_smaller_contribution_runs_out_before_the_target(underweight, client):
    """R$ 100 into a R$ 1.100 base: the target wants R$ 120, cash has 100."""
    headers, portfolio_id = underweight

    plan = _plan(client, headers, portfolio_id, amount="100")

    line = plan["allocations"][0]
    assert Decimal(line["amount"]) == Decimal("100.00")
    assert Decimal(line["needed"]) == Decimal("120.00")
    assert line["limited_by"] == "CONTRIBUTION_REMAINING"


def test_the_sector_ceiling_bites_through_an_unrated_holding(seeded, client):
    """The `seeded` portfolio is 100% Energia, R$ 800 of it unrateable.

    AAAA3 is under its target once the contribution dilutes it, and is
    still refused: its sector is already far past the 40% ceiling, and
    the unrated name holding it there has no target of its own to stop.
    """
    headers, portfolio_id = seeded

    plan = _plan(client, headers, portfolio_id)

    assert plan["allocations"] == []
    assert _skipped(plan)["AAAA3"] == "SECTOR_LIMIT_REACHED"
    assert Decimal(plan["unallocated"]) == Decimal(plan["contribution"])


@pytest.fixture
def on_target_today(client):
    """AAAA3 held at exactly its 20% target, in a sector of its own."""
    headers = _auth_headers(client, "rp-dilution@example.com")
    _seed_benchmarks(client, headers)
    rated = _seed_asset(client, headers, "AAAA3", sector="Energia")
    unrated = _seed_asset(client, headers, "BBBB3", sector="Bancos", statements=False)
    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, rated, "2", "100")
    _buy(client, headers, portfolio_id, unrated, "8", "100")
    return headers, portfolio_id


def test_a_position_on_target_today_is_still_bought_when_the_money_dilutes_it(
    on_target_today, client
):
    """The drift table and the plan disagree, and both are right.

    AAAA3 is R$ 200 of R$ 1.000: exactly its 20% target, so `/rebalance`
    calls it on target. The R$ 1.000 contribution doubles the base, and
    the same R$ 200 is 10% of R$ 2.000 — so the plan buys R$ 200 more to
    put it back where it belongs.
    """
    headers, portfolio_id = on_target_today

    table = _rebalance(client, headers, portfolio_id)
    assert _rows(table)["AAAA3"]["status"] == "ON_TARGET"

    plan = _plan(client, headers, portfolio_id)
    assert _placed(plan) == {"AAAA3": Decimal("200.00")}
    assert plan["allocations"][0]["limited_by"] == "TARGET_WEIGHT"
    assert Decimal(plan["allocations"][0]["weight_after"]) == Decimal("0.20")


def test_the_plan_records_all_three_versions(underweight, client):
    headers, portfolio_id = underweight

    plan = _plan(client, headers, portfolio_id)

    assert plan["rules_version"]
    assert plan["model_version"]
    assert plan["formula_version"]
