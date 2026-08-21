"""Tests for the rebalancing plan.

Pure function, hand-computed expectations (AGENTS.md rule 68). Every
amount below was worked out from the target and the base — `target *
base - held` — rather than read back from a first run.

The plan is built on a real `PortfolioTargets`, produced by
`compute_targets`, rather than on a hand-assembled one. What is under
test includes how the two fit together, and a stubbed drift table could
not show that.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from app.domain.recommendations.allocation import (
    DEFAULT_POLICY,
    MAX_SECTOR_WEIGHT,
    Candidate,
    Exclusion,
    Limit,
)
from app.domain.recommendations.rebalancing import rebalance_contribution
from app.domain.recommendations.scoring import (
    PILLAR_WEIGHTS,
    AssetScore,
    SubScore,
    compose,
)
from app.domain.recommendations.targets import compute_targets

CONTRIBUTION = Decimal(1000)


def _score(
    quality: str | None = None,
    valuation: str | None = None,
    growth: str | None = None,
    risk: str | None = None,
    diversification: str | None = "100",
) -> AssetScore:
    return compose(
        [
            SubScore(
                name=name,
                value=None if raw is None else Decimal(raw),
                weight=PILLAR_WEIGHTS[name],
            )
            for name, raw in (
                ("quality", quality),
                ("valuation", valuation),
                ("growth", growth),
                ("risk", risk),
                ("diversification", diversification),
            )
        ]
    )


def _flat(value: str) -> AssetScore:
    return _score(value, value, value, value)


def _candidate(
    ticker: str,
    score: AssetScore | None = None,
    sector: str | None = "Energia",
    held: str = "0",
) -> Candidate:
    return Candidate(
        ticker=ticker,
        asset_id=abs(hash(ticker)) % 10_000,
        name=f"{ticker} SA",
        sector=sector,
        score=score if score is not None else _flat("80"),
        held_amount=Decimal(held),
    )


def _plan(candidates, invested="0", sectors=None, contribution=CONTRIBUTION, **policy):
    targets = compute_targets(
        candidates,
        invested=Decimal(invested),
        policy=replace(DEFAULT_POLICY, **policy) if policy else DEFAULT_POLICY,
    )
    return rebalance_contribution(
        targets,
        sector_amounts={k: Decimal(v) for k, v in (sectors or {}).items()},
        contribution=contribution,
        policy=replace(DEFAULT_POLICY, **policy) if policy else DEFAULT_POLICY,
    )


def _amounts(plan):
    return {item.ticker: item.amount for item in plan.allocations}


def _reasons(plan):
    return {item.ticker: item.reason for item in plan.skipped}


def _details(plan):
    return {item.ticker: item.detail for item in plan.skipped}


# -- sizing ------------------------------------------------------------


def test_an_allocation_stops_at_the_target():
    """`target * base - held`, and not a centavo past it.

    Five equal-merit names in five sectors each target 20%. Nothing is
    held and the contribution is R$ 1.000, so the base is R$ 1.000 and
    each one needs exactly R$ 200 to land on its target.
    """
    plan = _plan(
        [_candidate(f"{letter * 4}3", _flat("80"), sector=letter) for letter in "ABCDE"]
    )

    assert _amounts(plan) == {f"{letter * 4}3": Decimal("200.00") for letter in "ABCDE"}
    assert all(item.limited_by is Limit.TARGET_WEIGHT for item in plan.allocations)
    assert plan.allocated == CONTRIBUTION
    assert plan.unallocated == 0


def test_the_target_is_measured_against_the_portfolio_after_the_money_goes_in():
    """The base grows, so the amount needed is not `gap * invested`.

    R$ 1.000 already held in AAAA3, R$ 1.000 arriving, so the base is
    R$ 2.000 and the 20% target is R$ 400. AAAA3 holds R$ 1.000 already
    and is over; BBBB3 holds nothing and needs the whole R$ 400.
    """
    plan = _plan(
        [
            _candidate("AAAA3", _flat("80"), sector="A", held="1000"),
            _candidate("BBBB3", _flat("80"), sector="B"),
        ],
        invested="1000",
        sectors={"A": "1000"},
    )

    assert _amounts(plan) == {"BBBB3": Decimal("400.00")}
    assert _reasons(plan)["AAAA3"] is Exclusion.ABOVE_TARGET
    assert plan.unallocated == Decimal("600.00")


def test_the_biggest_gap_is_funded_first():
    """Rule 34's priority, and the money runs out in that order.

    Three names targeting 1/3 each under a relaxed ceiling, against a
    R$ 3.000 portfolio taking R$ 1.000. Base R$ 4.000, so every target
    is R$ 1.333,33.

    AAAA3 holds nothing, so its gap is the largest and it goes first —
    it could take R$ 1.333,33 and only R$ 1.000 exists. BBBB3 is
    underweight too, by half as much, and finds nothing left. CCCC3 is
    over its target and is not touched at all.
    """
    plan = _plan(
        [
            _candidate("AAAA3", _flat("80"), sector="A"),
            _candidate("BBBB3", _flat("80"), sector="B", held="500"),
            _candidate("CCCC3", _flat("80"), sector="C", held="2500"),
        ],
        invested="3000",
        sectors={"B": "500", "C": "2500"},
        max_asset_weight=Decimal("0.40"),
    )

    assert _amounts(plan) == {"AAAA3": CONTRIBUTION}
    assert plan.allocations[0].rank == 1
    assert plan.allocations[0].limited_by is Limit.CONTRIBUTION_REMAINING
    # 1/3 of R$ 4.000: the 40% ceiling was relaxed enough not to bind.
    assert plan.allocations[0].needed == Decimal("1333.33")
    assert _reasons(plan) == {
        "BBBB3": Exclusion.CONTRIBUTION_EXHAUSTED,
        "CCCC3": Exclusion.ABOVE_TARGET,
    }


def test_the_per_asset_ceiling_can_never_bind():
    """It is evaluated, and the target always gets there first.

    No target may exceed `max_asset_weight`, so the money that reaches
    the target is never more than the ceiling allows. The test pins the
    invariant rather than a number.
    """
    plan = _plan(
        [
            _candidate(f"{letter * 4}3", _flat("80"), sector=letter)
            for letter in "ABCDE"
        ],
        invested="5000",
        sectors={letter: "1000" for letter in "ABCDE"},
    )

    assert plan.allocations
    assert all(item.limited_by is not Limit.ASSET_WEIGHT for item in plan.allocations)


# -- the band ----------------------------------------------------------


def test_an_asset_inside_the_band_is_left_alone():
    """Buying a gap of nothing is churn, and the band exists to say so.

    Two rated names capped at 20% each. AAAA3 holds R$ 400 of a R$ 1.000
    portfolio, and the R$ 1.000 contribution makes the base R$ 2.000 —
    so it lands on exactly 20% without being bought at all.
    """
    plan = _plan(
        [
            _candidate("AAAA3", _flat("80"), sector="A", held="400"),
            _candidate("BBBB3", _flat("80"), sector="B", held="600"),
        ],
        invested="1000",
        sectors={"A": "400", "B": "600"},
    )

    assert _reasons(plan)["AAAA3"] is Exclusion.WITHIN_BAND
    assert "churn" in _details(plan)["AAAA3"]
    assert plan.allocations == ()


def test_a_narrower_band_funds_what_a_wider_one_would_not():
    """Rule 32: the band is the investor's to set, like every limit.

    R$ 4.000 invested plus R$ 1.000 makes a base of R$ 5.000. AAAA3
    holds R$ 900, so it lands on 18% against a 20% target: a gap of
    exactly 2 p.p., which the default band calls on-target and a
    0.1 p.p. band calls a R$ 100 order.
    """
    candidates = [
        _candidate("AAAA3", _flat("80"), sector="A", held="900"),
        _candidate("BBBB3", _flat("80"), sector="B", held="3100"),
    ]
    sectors = {"A": "900", "B": "3100"}

    wide = _plan(candidates, invested="4000", sectors=sectors)
    narrow = _plan(
        candidates,
        invested="4000",
        sectors=sectors,
        rebalance_band=Decimal("0.001"),
    )

    assert _reasons(wide)["AAAA3"] is Exclusion.WITHIN_BAND
    assert _amounts(narrow) == {"AAAA3": Decimal("100.00")}


def test_the_gate_runs_on_the_portfolio_the_contribution_creates():
    """The bug the real database caught, pinned.

    AAAA3 holds R$ 300 of a R$ 1.200 portfolio — 25% against a 20%
    target, and therefore *above* it on the weights the drift table
    reports. Judged there, it would be refused, the whole R$ 1.000 would
    sit in cash, and the position would settle at 300/2.200 = 13.6%:
    further below its target than it started above it.

    Judged on the base the money creates, it needs
    0.20 * 2.200 - 300 = R$ 140, and gets exactly that.
    """
    candidates = [
        _candidate("AAAA3", _flat("80"), sector="A", held="300"),
        _candidate("XXXX3", _score(risk="30"), sector="B", held="900"),
    ]

    plan = _plan(candidates, invested="1200", sectors={"A": "300", "B": "900"})

    assert plan.base_value == Decimal("2200.00")
    assert _amounts(plan) == {"AAAA3": Decimal("140.00")}
    assert plan.allocations[0].limited_by is Limit.TARGET_WEIGHT
    # The drift table still reports it as overweight, because on today's
    # portfolio it is. Both numbers are on the line.
    assert plan.allocations[0].current_weight == Decimal("0.250000")
    assert plan.allocations[0].weight_gap == Decimal("-0.050000")
    assert plan.allocations[0].gap_after == 0


# -- what gets nothing -------------------------------------------------


def test_an_asset_above_its_target_is_never_sold():
    """The plan has no sell side, and says why in words."""
    plan = _plan(
        [
            _candidate("AAAA3", _flat("80"), sector="A", held="900"),
            _candidate("BBBB3", _flat("80"), sector="B", held="100"),
        ],
        invested="1000",
        sectors={"A": "900", "B": "100"},
    )

    assert _reasons(plan)["AAAA3"] is Exclusion.ABOVE_TARGET
    detail = _details(plan)["AAAA3"]
    assert "dilution" in detail
    assert all(item.amount > 0 for item in plan.allocations)


def test_an_asset_with_no_target_carries_the_tables_own_verdict():
    """One reason, stated once. Re-judging it here would let them drift."""
    plan = _plan(
        [
            _candidate("AAAA3", _flat("80"), sector="A"),
            _candidate("XXXX3", _score(risk="30"), sector="B", held="500"),
        ],
        invested="500",
        sectors={"B": "500"},
    )

    skipped = {item.ticker: item for item in plan.skipped}
    assert skipped["XXXX3"].reason is Exclusion.NO_MERIT_SCORE
    assert "fewer than two" in skipped["XXXX3"].detail


def test_the_sector_ceiling_still_bites_through_an_unrated_holding():
    """The one ceiling the target does not subsume.

    Half the portfolio sits in an unrated name in Bancos, which has no
    target of its own to hold it back. A rated name in the same sector
    would be funded to its 20% target and put Bancos past 40%, so the
    sector ceiling cuts it short.

    Base is R$ 2.000 and Bancos already holds R$ 1.000, so its room is
    0.40 * 2.000 - 1.000 = -200: no room at all.
    """
    plan = _plan(
        [
            _candidate("AAAA3", _flat("80"), sector="Bancos"),
            _candidate("XXXX3", _score(risk="30"), sector="Bancos", held="1000"),
        ],
        invested="1000",
        sectors={"Bancos": "1000"},
    )

    assert _reasons(plan)["AAAA3"] is Exclusion.SECTOR_LIMIT_REACHED
    assert plan.allocated == 0
    assert plan.unallocated == CONTRIBUTION


def test_a_sector_with_room_for_only_part_of_the_gap_is_cut_short():
    """Base R$ 2.000, Bancos holds R$ 700, so its room is R$ 100."""
    plan = _plan(
        [
            _candidate("AAAA3", _flat("80"), sector="Bancos"),
            _candidate("XXXX3", _score(risk="30"), sector="Bancos", held="700"),
            _candidate("CCCC3", _score(risk="30"), sector="Outros", held="300"),
        ],
        invested="1000",
        sectors={"Bancos": "700", "Outros": "300"},
    )

    assert _amounts(plan) == {"AAAA3": Decimal("100.00")}
    assert plan.allocations[0].limited_by is Limit.SECTOR_WEIGHT
    assert plan.allocations[0].needed == Decimal("400.00")  # 0.20 * 2000
    assert MAX_SECTOR_WEIGHT * plan.base_value == Decimal("800.000")


def test_a_slice_below_the_minimum_ticket_is_not_emitted():
    """A gap worth reporting is not always a gap worth an order.

    AAAA3 holds R$ 170 of a R$ 1.000 portfolio — 17% against a 20%
    target, a 3 p.p. gap that clears the band. But the contribution is
    only R$ 100, so the base is R$ 1.100 and closing the gap outright
    takes 0.20 * 1.100 - 170 = R$ 50. Below the minimum ticket that is
    more fee than investment, so the plan emits nothing and says which
    rule stopped it.
    """
    plan = _plan(
        [
            _candidate("AAAA3", _flat("80"), sector="A", held="170"),
            _candidate("XXXX3", _score(risk="30"), sector="B", held="830"),
        ],
        invested="1000",
        sectors={"A": "170", "B": "830"},
        contribution=Decimal(100),
    )

    assert plan.allocations == ()
    assert _reasons(plan)["AAAA3"] is Exclusion.BELOW_MINIMUM_TICKET
    assert plan.unallocated == Decimal(100)


def test_the_plan_funds_at_most_max_positions():
    plan = _plan(
        [
            _candidate(f"{letter * 4}3", _flat("80"), sector=letter)
            for letter in "ABCDEF"
        ],
        max_positions=2,
    )

    assert len(plan.allocations) == 2
    assert set(_reasons(plan).values()) == {Exclusion.MAX_POSITIONS_REACHED}


def test_a_non_positive_contribution_is_refused():
    with pytest.raises(ValueError, match="positive"):
        _plan([_candidate("AAAA3")], contribution=Decimal(0))


# -- what the plan reports about itself --------------------------------


def test_the_money_always_adds_up():
    plan = _plan(
        [_candidate(f"{letter * 4}3", _flat("80"), sector=letter) for letter in "ABC"]
    )

    assert plan.allocated + plan.unallocated == plan.contribution
    assert plan.base_value == plan.contribution


def test_the_distance_left_is_measured_after_the_money_lands():
    """Three names targeting 20% each; only 60% of the portfolio has one.

    Before: nothing held, so each gap is the full 20% and the total
    underweight is 60%. After: R$ 200 into each of the three on a
    R$ 1.000 base puts all three exactly on target, and the distance
    left is zero.
    """
    plan = _plan(
        [_candidate(f"{letter * 4}3", _flat("80"), sector=letter) for letter in "ABC"]
    )

    assert plan.underweight_before == Decimal("0.600000")
    assert plan.underweight_after == 0


def test_unplaceable_money_leaves_the_portfolio_further_away():
    """Cash inside the base dilutes the gaps it could not close.

    A single rated name targets 20% of a R$ 1.000 base and takes R$ 200.
    The R$ 800 that stays as cash is not neutral: it is in the
    denominator, and there is nothing for it to be a weight of. Netting
    it away would flatter the plan, so both figures are reported.
    """
    plan = _plan(
        [
            _candidate("AAAA3", _flat("80"), sector="A"),
            _candidate("XXXX3", _score(risk="30"), sector="B"),
        ]
    )

    assert _amounts(plan) == {"AAAA3": Decimal("200.00")}
    assert plan.unallocated == Decimal("800.00")
    assert plan.underweight_before == Decimal("0.200000")
    assert plan.underweight_after == 0


def test_versions_are_reported():
    """Rule 30: the scores, the target model and these rules, all three."""
    plan = _plan([_candidate("AAAA3", _flat("80"))])

    assert plan.rules_version == "1.0.0"
    assert plan.model_version
    assert plan.formula_version


def test_the_result_does_not_depend_on_the_order_candidates_arrive_in():
    """Rule 113, end to end through the target model and the plan."""
    candidates = [
        _candidate("AAAA3", _flat("90"), sector="A"),
        _candidate("BBBB3", _flat("70"), sector="B", held="300"),
        _candidate("CCCC3", _flat("80"), sector="C", held="700"),
    ]
    sectors = {"A": "0", "B": "300", "C": "700"}

    forward = _plan(candidates, invested="1000", sectors=sectors)
    backward = _plan(list(reversed(candidates)), invested="1000", sectors=sectors)

    assert _amounts(forward) == _amounts(backward)
    assert [item.ticker for item in forward.allocations] == [
        item.ticker for item in backward.allocations
    ]
