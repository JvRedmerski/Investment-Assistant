"""Tests for `app.domain.ai.facts`.

The figures below are the ones the W11-004 fix actually produced against
the real database (portfolio 12,4% against the CDI over the shared
window, excess +7,1 p.p., volatility 22,5%, drawdown -13,4%). Using them
rather than round invented numbers keeps this file honest about what a
fact pack looks like in production.

What is being pinned: the builders **select and render**, and never
compute. If a test here ever needs arithmetic to state its expectation,
a builder has started doing something it must not do.
"""

from datetime import date
from decimal import Decimal

from app.domain.ai import facts as facts_module
from app.domain.ai.facts import (
    asset_score_facts,
    contribution_plan_facts,
    portfolio_performance_facts,
)
from app.domain.ai.schemas import ExplanationTopic, FactUnit
from app.domain.benchmarks.schemas import (
    BenchmarkComparisonResponse,
    SeriesPerformanceResponse,
)
from app.domain.recommendations.schemas import (
    AllocationPolicyResponse,
    AllocationResponse,
    AssetScoreResponse,
    ContributionPlanResponse,
    SkippedCandidateResponse,
    SubScoreResponse,
)
from app.quant.returns import Periodicity


def _series(
    total: str | None,
    annualised: str | None,
    volatility: str | None,
    drawdown: str | None,
) -> SeriesPerformanceResponse:
    return SeriesPerformanceResponse(
        start_date=date(2025, 8, 15),
        end_date=date(2026, 8, 21),
        observations=252,
        periodicity=Periodicity.DAILY,
        total_return=None if total is None else Decimal(total),
        annualised_return=None if annualised is None else Decimal(annualised),
        volatility=None if volatility is None else Decimal(volatility),
        max_drawdown=None if drawdown is None else Decimal(drawdown),
    )


def _comparison(**overrides: object) -> BenchmarkComparisonResponse:
    payload: dict[str, object] = {
        "benchmark_code": "CDI",
        "benchmark_name": "CDI",
        "subject": _series("0.1238", "0.1191", "0.2251", "-0.1341"),
        "benchmark": _series("0.0527", "0.0508", "0.0009", "0"),
        "excess_return": Decimal("0.0711"),
        "return_ratio": Decimal("2.3492"),
        "beta": None,
        "sharpe": Decimal("0.8351"),
        "sortino": Decimal("1.1204"),
        "risk_free_rate": Decimal("0.0527"),
    }
    payload.update(overrides)
    return BenchmarkComparisonResponse(**payload)  # type: ignore[arg-type]


def _by_key(pack, key: str):
    return next(fact for fact in pack.facts if fact.key == key)


# -- portfolio performance -------------------------------------------


def test_performance_pack_renders_each_figure_as_the_screen_shows_it():
    pack = portfolio_performance_facts("Carteira Local", 1, _comparison())

    assert pack.topic is ExplanationTopic.PORTFOLIO_PERFORMANCE
    assert pack.subject == "Carteira Local"
    assert _by_key(pack, "portfolio.total_return").formatted == "12,4%"
    assert _by_key(pack, "benchmark.total_return").formatted == "5,3%"
    assert _by_key(pack, "portfolio.volatility").formatted == "22,5%"
    assert _by_key(pack, "portfolio.max_drawdown").formatted == "-13,4%"
    assert _by_key(pack, "comparison.sharpe").formatted == "0,84"


def test_the_excess_is_carried_in_points_and_the_return_in_percent():
    """Both are fractions in the database and different quantities."""
    pack = portfolio_performance_facts("Carteira Local", 1, _comparison())

    excess = _by_key(pack, "comparison.excess_return")
    assert excess.unit is FactUnit.POINTS
    assert excess.formatted == "+7,1 p.p."

    total = _by_key(pack, "portfolio.total_return")
    assert total.unit is FactUnit.PERCENT
    assert total.formatted == "12,4%"


def test_the_return_ratio_is_rendered_as_the_percent_of_cdi_idiom():
    pack = portfolio_performance_facts("Carteira Local", 1, _comparison())
    assert _by_key(pack, "comparison.return_ratio").formatted == "234,9%"


def test_every_fact_names_the_endpoint_that_produced_it():
    """Rule 112: a figure is auditable only if it can be traced back."""
    pack = portfolio_performance_facts("Carteira Local", 7, _comparison())
    expected = "GET /api/v1/portfolios/7/benchmarks/CDI"
    assert {fact.source for fact in pack.facts} == {expected}


def test_an_absent_metric_stays_in_the_pack_as_absent():
    """Dropping it would let the model assume it simply did not matter."""
    pack = portfolio_performance_facts("Carteira Local", 1, _comparison())

    beta = _by_key(pack, "comparison.beta")
    assert beta.value is None
    assert beta.formatted == "—"
    assert beta in pack.unavailable
    assert beta not in pack.available


def test_the_window_is_reported_once_because_both_sides_share_it():
    pack = portfolio_performance_facts("Carteira Local", 1, _comparison())
    assert _by_key(pack, "window.start").formatted == "15/08/2025"
    assert _by_key(pack, "window.end").formatted == "21/08/2026"
    assert _by_key(pack, "window.observations").formatted == "252"


# -- contribution plan -----------------------------------------------


def _policy() -> AllocationPolicyResponse:
    return AllocationPolicyResponse(
        max_asset_weight=Decimal("0.20"),
        max_sector_weight=Decimal("0.35"),
        max_share_per_position=Decimal("0.40"),
        max_positions=15,
        min_ticket=Decimal(100),
        min_coverage=Decimal("0.40"),
        min_score=Decimal(50),
        coverage_tier_width=Decimal("0.25"),
        rebalance_band=Decimal("0.05"),
        require_sector=False,
    )


def _allocation(ticker: str, amount: str, rank: int) -> AllocationResponse:
    return AllocationResponse(
        ticker=ticker,
        asset_id=rank,
        name=f"{ticker} SA",
        sector="Petróleo",
        amount=Decimal(amount),
        rank=rank,
        final_score=Decimal("76.7231"),
        coverage=Decimal("0.75"),
        coverage_tier=1,
        headroom=Decimal(250),
        limited_by="MAX_ASSET_WEIGHT",
        weight_before=Decimal("0.1832"),
        weight_after=Decimal("0.2000"),
        sub_scores=[],
    )


def _plan(allocations, skipped) -> ContributionPlanResponse:
    return ContributionPlanResponse(
        portfolio_id=1,
        rules_version="alloc-v1",
        formula_version="score-v1",
        policy=_policy(),
        contribution=Decimal(1000),
        allocated=Decimal(900),
        unallocated=Decimal(100),
        base_value=Decimal(25000),
        allocations=allocations,
        skipped=skipped,
    )


def test_plan_pack_carries_the_money_and_the_rule_that_sized_it():
    plan = _plan([_allocation("PETR4", "400", 1)], [])
    pack = contribution_plan_facts("Carteira Local", plan)

    assert pack.topic is ExplanationTopic.CONTRIBUTION_PLAN
    assert _by_key(pack, "plan.contribution").formatted == "R$ 1.000,00"
    assert _by_key(pack, "plan.unallocated").formatted == "R$ 100,00"
    assert _by_key(pack, "allocation.PETR4.amount").formatted == "R$ 400,00"
    assert _by_key(pack, "allocation.PETR4.limited_by").value == "MAX_ASSET_WEIGHT"
    assert _by_key(pack, "allocation.PETR4.weight_after").formatted == "20,0%"


def test_the_policy_ceilings_travel_as_facts_not_as_prompt_prose():
    """Rule 43: a limit is a value with a source, never a sentence."""
    pack = contribution_plan_facts("Carteira Local", _plan([], []))
    assert _by_key(pack, "policy.max_asset_weight").formatted == "20,0%"
    assert _by_key(pack, "policy.max_sector_weight").formatted == "35,0%"
    assert _by_key(pack, "policy.min_ticket").formatted == "R$ 100,00"


def test_a_skipped_candidate_carries_the_rule_that_stopped_it():
    skipped = SkippedCandidateResponse(
        ticker="MGLU3",
        asset_id=9,
        name="Magazine Luiza",
        reason="BELOW_MIN_COVERAGE",
        detail="cobertura 0,25 abaixo do mínimo",
        final_score=None,
        coverage=Decimal("0.25"),
    )
    pack = contribution_plan_facts("Carteira Local", _plan([], [skipped]))
    fact = _by_key(pack, "skipped.MGLU3.reason")
    assert fact.value == "BELOW_MIN_COVERAGE: cobertura 0,25 abaixo do mínimo"


def test_truncation_is_reported_as_a_fact_rather_than_happening_silently():
    """A prompt that outgrows the token limit must not drop facts quietly."""
    allocations = [
        _allocation(f"AAA{i}", "50", i)
        for i in range(1, facts_module.MAX_PLAN_LINES + 4)
    ]
    pack = contribution_plan_facts("Carteira Local", _plan(allocations, []))

    assert _by_key(pack, "plan.lines_omitted").formatted == "3"
    assert _by_key(pack, "allocation.AAA1.amount") is not None
    keys = {fact.key for fact in pack.facts}
    assert "allocation.AAA9.amount" not in keys


def test_a_plan_that_fits_reports_nothing_omitted():
    pack = contribution_plan_facts("Carteira Local", _plan([], []))
    assert _by_key(pack, "plan.lines_omitted").formatted == "0"


# -- asset score -----------------------------------------------------


def _score(**overrides: object) -> AssetScoreResponse:
    payload: dict[str, object] = {
        "ticker": "PETR4",
        "asset_id": 1,
        "name": "Petrobras",
        "sector": "Petróleo",
        "formula_version": "score-v1",
        "final_score": Decimal("76.7231"),
        "coverage": Decimal("0.75"),
        "sub_scores": [
            SubScoreResponse(
                name="quality",
                value=Decimal("81.4"),
                weight=Decimal("0.25"),
                components={"roe": Decimal(88)},
                missing=(),
            ),
            SubScoreResponse(
                name="growth",
                value=None,
                weight=Decimal("0.20"),
                components={},
                missing=("revenue_cagr", "earnings_cagr"),
            ),
        ],
    }
    payload.update(overrides)
    return AssetScoreResponse(**payload)  # type: ignore[arg-type]


def test_score_pack_reports_coverage_next_to_the_score():
    pack = asset_score_facts(_score(), portfolio_id=1)

    assert pack.topic is ExplanationTopic.ASSET_SCORE
    assert pack.subject == "PETR4"
    assert _by_key(pack, "score.final").formatted == "76,72"
    assert _by_key(pack, "score.coverage").formatted == "75,0%"
    assert _by_key(pack, "score.formula_version").value == "score-v1"


def test_a_pillar_without_data_names_the_inputs_that_were_missing():
    pack = asset_score_facts(_score(), portfolio_id=1)

    growth = _by_key(pack, "pillar.growth.value")
    assert growth.value is None
    assert growth.formatted == "—"
    assert _by_key(pack, "pillar.growth.missing").value == "revenue_cagr, earnings_cagr"


def test_a_complete_pillar_lists_no_missing_inputs():
    pack = asset_score_facts(_score(), portfolio_id=1)
    keys = {fact.key for fact in pack.facts}
    assert "pillar.quality.missing" not in keys
    assert _by_key(pack, "pillar.quality.value").formatted == "81,40"


def test_an_asset_with_no_sector_renders_the_absence():
    pack = asset_score_facts(_score(sector=None), portfolio_id=1)
    assert _by_key(pack, "asset.sector").formatted == "—"
    assert _by_key(pack, "asset.sector").value is None
