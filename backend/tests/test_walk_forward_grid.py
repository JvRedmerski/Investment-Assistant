"""Tests for the hypothesis grid and the segment objective (W14-002).

Pure: policies in, policies out; a price series in, measurements out. No
session, no engine.

What is worth testing here is not arithmetic — `quant` already owns that
— but the two properties rule 60 turns on: the grid varies **one** field
per candidate and never becomes a cross product, and a candidate that
cannot be scored is absent from the ranking rather than last in it.
"""

from dataclasses import fields, replace
from datetime import date, timedelta
from decimal import Decimal

from app.domain.backtesting.grid import (
    BASELINE,
    WALK_FORWARD_GRID_VERSION,
    policy_grid,
)
from app.domain.backtesting.objectives import (
    SegmentMetrics,
    SelectionObjective,
    measure_segment,
    objective_value,
)
from app.domain.recommendations.allocation import DEFAULT_POLICY
from app.quant.returns import PricePoint

FIRST = date(2024, 1, 1)


def _series(values: list[str], first: date = FIRST) -> list[PricePoint]:
    return [
        PricePoint(date=first + timedelta(days=offset), adjusted_close=Decimal(value))
        for offset, value in enumerate(values)
    ]


def _differing_fields(left, right) -> list[str]:
    return [
        field.name
        for field in fields(left)
        if getattr(left, field.name) != getattr(right, field.name)
    ]


# -- the grid is a hypothesis set -------------------------------------


def test_the_baseline_is_the_policy_given_and_comes_first():
    tightened = replace(DEFAULT_POLICY, max_asset_weight=Decimal("0.15"))
    grid = policy_grid(tightened)

    assert grid[0].name == BASELINE
    assert grid[0].policy == tightened


def test_every_variant_differs_from_the_baseline_in_exactly_one_field():
    """One question per candidate — never a cross product (rule 60)."""
    grid = policy_grid(DEFAULT_POLICY)

    for candidate in grid[1:]:
        assert _differing_fields(DEFAULT_POLICY, candidate.policy) != []
        assert len(_differing_fields(DEFAULT_POLICY, candidate.policy)) == 1


def test_the_grid_stays_small_and_every_candidate_states_its_question():
    grid = policy_grid(DEFAULT_POLICY)

    assert len(grid) == 7
    assert len({candidate.name for candidate in grid}) == 7
    for candidate in grid:
        assert candidate.question.endswith("?")


def test_the_variants_are_built_from_the_callers_own_policy():
    """An investor who tightened their limits is asking about *theirs*."""
    theirs = replace(DEFAULT_POLICY, max_share_per_position=Decimal("0.25"))
    grid = policy_grid(theirs)

    for candidate in grid:
        assert candidate.policy.max_share_per_position == Decimal("0.25")


def test_a_variant_that_lands_on_the_baseline_is_dropped_not_repeated():
    already = replace(DEFAULT_POLICY, min_score=Decimal(30))
    grid = policy_grid(already)

    names = [candidate.name for candidate in grid]
    assert names[0] == BASELINE
    assert "min-score-30" not in names
    assert "min-score-70" in names
    assert len({candidate.policy for candidate in grid}) == len(grid)


def test_the_grid_is_versioned_and_deterministic():
    assert WALK_FORWARD_GRID_VERSION == "1.0.0"
    assert policy_grid(DEFAULT_POLICY) == policy_grid(DEFAULT_POLICY)


# -- measuring a segment ----------------------------------------------


def test_a_rising_segment_is_measured_with_the_projects_own_quant():
    index = _series(["100", "101", "102", "103", "104"])

    metrics = measure_segment(index)

    assert metrics.observations == 5
    assert metrics.total_return == Decimal("0.04")
    assert metrics.max_drawdown == Decimal(0)
    assert metrics.volatility is not None


def test_a_drawdown_is_reported_as_a_negative_fraction():
    index = _series(["100", "120", "90", "95"])

    assert measure_segment(index).max_drawdown == Decimal("-0.25")


def test_sharpe_is_none_without_a_risk_free_rate_and_a_number_with_one():
    index = _series(["100", "101", "100", "102", "103", "101", "104"])

    assert measure_segment(index).sharpe is None
    assert measure_segment(index, Decimal("0.1075")).sharpe is not None


def test_a_segment_too_short_to_annualise_reports_no_cagr():
    """Five days is not a rate — `MIN_ANNUALISATION_DAYS` says so."""
    metrics = measure_segment(_series(["100", "101", "102", "103", "104"]))

    assert metrics.cagr is None
    assert metrics.total_return is not None


def test_an_empty_segment_measures_nothing_rather_than_zero():
    metrics = measure_segment([])

    assert metrics.observations == 0
    assert metrics.total_return is None
    assert metrics.volatility is None
    assert metrics.max_drawdown is None


# -- the objective ----------------------------------------------------


def _metrics(**overrides) -> SegmentMetrics:
    values = {
        "observations": 10,
        "total_return": Decimal("0.10"),
        "cagr": Decimal("0.12"),
        "volatility": Decimal("0.20"),
        "max_drawdown": Decimal("-0.05"),
        "sharpe": Decimal("0.80"),
        "sortino": Decimal("1.10"),
    }
    values.update(overrides)
    return SegmentMetrics(**values)


def test_each_objective_reads_its_own_figure():
    assert objective_value(_metrics(), SelectionObjective.SHARPE) == Decimal("0.80")
    assert objective_value(_metrics(), SelectionObjective.TOTAL_RETURN) == Decimal(
        "0.10"
    )


def test_a_missing_objective_is_none_and_not_a_zero():
    """No risk-free rate means unrankable, never 'ranked worst'."""
    assert objective_value(_metrics(sharpe=None), SelectionObjective.SHARPE) is None


def test_the_objective_set_is_closed_and_named_by_its_wire_value():
    assert {objective.value for objective in SelectionObjective} == {
        "sharpe",
        "total-return",
    }
