"""Tests for the contribution allocator.

Pure function, hand-computed expectations (AGENTS.md rule 68). Every
amount below was worked out from the constants in `allocation.py` — the
ceiling times the base, less what is already held — rather than read back
from a first run.

`_score` builds an `AssetScore` directly instead of going through the
pillars, because what is under test here is what the allocator does with
a score and a coverage, not how either was produced.
"""

from decimal import Decimal

import pytest

from app.domain.recommendations.allocation import (
    DEFAULT_POLICY,
    MAX_ASSET_WEIGHT,
    MAX_SECTOR_WEIGHT,
    AllocationPolicy,
    Candidate,
    Exclusion,
    Limit,
    allocate_contribution,
)
from app.domain.recommendations.scoring import (
    ASSET_WEIGHT_SCALE,
    PILLAR_WEIGHTS,
    SECTOR_WEIGHT_SCALE,
    AssetScore,
    SubScore,
)

CONTRIBUTION = Decimal(1000)


def _score(value: Decimal | None, coverage: Decimal) -> AssetScore:
    """An `AssetScore` with the two fields the allocator reads.

    `sub_scores` carries one available pillar and one absent one, so the
    "why is there no final score" message has something to name.
    """
    return AssetScore(
        formula_version="test",
        sub_scores=(
            SubScore(name="risk", value=value, weight=PILLAR_WEIGHTS["risk"]),
            SubScore(name="growth", value=None, weight=PILLAR_WEIGHTS["growth"]),
        ),
        final_score=value,
        coverage=coverage,
    )


def _candidate(
    ticker: str,
    score: str = "80",
    coverage: str = "1.0",
    sector: str | None = "Energia",
    held: str = "0",
    asset_id: int | None = None,
) -> Candidate:
    return Candidate(
        ticker=ticker,
        asset_id=asset_id if asset_id is not None else abs(hash(ticker)) % 10_000,
        name=f"{ticker} SA",
        sector=sector,
        score=_score(Decimal(score), Decimal(coverage)),
        held_amount=Decimal(held),
    )


def _plan(candidates, invested="0", sectors=None, contribution=CONTRIBUTION, **policy):
    return allocate_contribution(
        candidates,
        invested=Decimal(invested),
        sector_amounts={
            name: Decimal(amount) for name, amount in (sectors or {}).items()
        },
        contribution=contribution,
        policy=AllocationPolicy(**policy) if policy else DEFAULT_POLICY,
    )


def _amounts(plan) -> dict[str, Decimal]:
    return {item.ticker: item.amount for item in plan.allocations}


def _reasons(plan) -> dict[str, Exclusion]:
    return {item.ticker: item.reason for item in plan.skipped}


# -- the limits are the ones the score already uses -------------------


def test_the_ceilings_are_the_diversification_scales_themselves():
    """Not a second copy that could drift.

    The Diversification pillar scores zero exactly where the allocator
    stops adding. Two constants with the same intent would be free to
    disagree until an asset scored well for diversifying into a position
    the allocator refuses to fund.
    """
    assert MAX_ASSET_WEIGHT is ASSET_WEIGHT_SCALE.at_zero
    assert MAX_SECTOR_WEIGHT is SECTOR_WEIGHT_SCALE.at_zero
    assert MAX_ASSET_WEIGHT == Decimal("0.20")
    assert MAX_SECTOR_WEIGHT == Decimal("0.40")


# -- the ordinary case ------------------------------------------------


def test_the_contribution_is_spread_over_the_best_ranked_candidates():
    """R$ 1.000 into a R$ 19.000 portfolio, three sectors, none of them held.

    The base is R$ 20.000, so the 20% ceiling is R$ 4.000 and never
    binds. The per-position share does: 40% of R$ 1.000 = R$ 400, so the
    top two take R$ 400 and the third takes what is left.
    """
    plan = _plan(
        [
            _candidate("AAAA3", score="90", sector="Energia"),
            _candidate("BBBB3", score="80", sector="Bancos"),
            _candidate("CCCC3", score="70", sector="Varejo"),
        ],
        invested="19000",
        sectors={"Outros": "19000"},
    )

    assert _amounts(plan) == {
        "AAAA3": Decimal("400.00"),
        "BBBB3": Decimal("400.00"),
        "CCCC3": Decimal("200.00"),
    }
    assert plan.allocated == Decimal("1000.00")
    assert plan.unallocated == Decimal("0.00")


def test_the_plan_always_balances():
    plan = _plan([_candidate("AAAA3")])

    assert plan.allocated + plan.unallocated == plan.contribution


def test_ranking_does_not_depend_on_the_order_candidates_arrive_in():
    """Rule 113: the same inputs give the same plan, however they are fed."""
    forward = [
        _candidate("AAAA3", score="90", asset_id=1, sector="Energia"),
        _candidate("BBBB3", score="80", asset_id=2, sector="Bancos"),
        _candidate("CCCC3", score="70", asset_id=3, sector="Varejo"),
    ]
    backward = list(reversed(forward))

    assert _amounts(_plan(forward)) == _amounts(_plan(backward))


def test_a_tie_on_score_is_broken_by_ticker_so_the_order_is_total():
    plan = _plan(
        [
            _candidate("ZZZZ3", score="80", sector="Bancos"),
            _candidate("AAAA3", score="80", sector="Energia"),
        ]
    )

    assert [item.ticker for item in plan.allocations] == ["AAAA3", "ZZZZ3"]


# -- coverage: the trap the ranking is built around -------------------


def test_a_better_covered_candidate_outranks_a_higher_score_below_it():
    """The whole point of the tiers.

    A score of 95 resting on 55% of the formula is not a better measure
    than a 60 resting on all of it — it is a different measure, and the
    gap is mostly the pillars that went missing. The fully covered asset
    is funded first, and the other only takes what is left.
    """
    plan = _plan(
        [
            _candidate("THIN4", score="95", coverage="0.55", sector="Bancos"),
            _candidate("FULL3", score="60", coverage="1.0", sector="Energia"),
        ]
    )

    assert [item.ticker for item in plan.allocations] == ["FULL3", "THIN4"]
    assert plan.allocations[0].coverage_tier > plan.allocations[1].coverage_tier


def test_scores_inside_one_tier_are_compared_normally():
    """0.80 and 0.85 coverage are the same band; the score decides."""
    plan = _plan(
        [
            _candidate("LOWER3", score="70", coverage="0.85", sector="Bancos"),
            _candidate("UPPER3", score="90", coverage="0.80", sector="Energia"),
        ]
    )

    assert [item.ticker for item in plan.allocations] == ["UPPER3", "LOWER3"]


def test_coverage_below_the_floor_is_not_a_candidate_at_all():
    """40% of the formula describes what is missing more than the asset."""
    plan = _plan([_candidate("THIN4", score="99", coverage="0.40")])

    assert plan.allocations == ()
    assert _reasons(plan) == {"THIN4": Exclusion.COVERAGE_BELOW_MINIMUM}
    assert "40.0%" in plan.skipped[0].detail


def test_an_unscorable_asset_is_reported_rather_than_dropped():
    """ "Nothing could be scored, and here is what was missing" is an answer."""
    candidate = Candidate(
        ticker="FIIX11",
        asset_id=7,
        name="Fundo Imobiliário",
        sector="Imóveis",
        score=_score(None, Decimal("0.15")),
    )

    plan = _plan([candidate])

    assert _reasons(plan) == {"FIIX11": Exclusion.NOT_SCORABLE}
    assert "growth" in plan.skipped[0].detail


def test_a_universe_with_nothing_fundable_allocates_nothing_and_says_why():
    plan = _plan(
        [
            _candidate("WEAK3", score="30"),
            _candidate("THIN4", score="99", coverage="0.20"),
        ]
    )

    assert plan.allocations == ()
    assert plan.allocated == Decimal("0.00")
    assert plan.unallocated == CONTRIBUTION
    assert _reasons(plan) == {
        "WEAK3": Exclusion.SCORE_BELOW_MINIMUM,
        "THIN4": Exclusion.COVERAGE_BELOW_MINIMUM,
    }


def test_a_score_below_the_minimum_is_not_bought_for_being_the_best_available():
    """There is always the CDI. A contribution is optional."""
    plan = _plan([_candidate("WEAK3", score="49"), _candidate("WORSE3", score="20")])

    assert plan.allocations == ()
    assert set(_reasons(plan).values()) == {Exclusion.SCORE_BELOW_MINIMUM}


# -- concentration ceilings (rule 32) ---------------------------------


def test_an_asset_at_its_ceiling_receives_nothing():
    """R$ 4.000 of a R$ 19.000 portfolio, and R$ 1.000 arriving.

    The base is R$ 20.000, so the 20% ceiling is R$ 4.000 — already
    reached. The money goes to the other candidate instead.
    """
    plan = _plan(
        [
            _candidate("FULL3", score="90", held="4000", sector="Energia"),
            _candidate("ROOM3", score="60", sector="Bancos"),
        ],
        invested="19000",
        sectors={"Energia": "4000"},
    )

    assert _reasons(plan) == {"FULL3": Exclusion.ASSET_LIMIT_REACHED}
    assert _amounts(plan) == {"ROOM3": Decimal("400.00")}
    assert "20.0%" in plan.skipped[0].detail


def test_an_allocation_is_cut_to_what_the_asset_ceiling_leaves():
    """R$ 3.750 held, base R$ 20.000: the 20% ceiling leaves R$ 250."""
    plan = _plan(
        [_candidate("NEAR3", score="90", held="3750", sector="Energia")],
        invested="19000",
        sectors={"Energia": "3750"},
    )

    (allocation,) = plan.allocations
    assert allocation.amount == Decimal("250.00")
    assert allocation.limited_by is Limit.ASSET_WEIGHT
    assert allocation.weight_after == Decimal("0.20")
    assert plan.unallocated == Decimal("750.00")


def test_two_assets_in_one_sector_share_a_single_sector_ceiling():
    """R$ 7.800 of a R$ 20.000 base leaves R$ 200 under the 40% ceiling.

    Charging each candidate the full room would let the pair breach it
    together — the first takes the R$ 200 and the second finds nothing.
    """
    plan = _plan(
        [
            _candidate("BANK3", score="90", sector="Bancos"),
            _candidate("BANK4", score="80", sector="Bancos"),
            _candidate("ENER3", score="70", sector="Energia"),
        ],
        invested="19000",
        sectors={"Bancos": "7800"},
    )

    assert _amounts(plan) == {"BANK3": Decimal("200.00"), "ENER3": Decimal("400.00")}
    assert _reasons(plan) == {"BANK4": Exclusion.SECTOR_LIMIT_REACHED}
    assert plan.allocations[0].limited_by is Limit.SECTOR_WEIGHT


def test_a_sector_already_over_its_ceiling_receives_nothing():
    plan = _plan(
        [_candidate("BANK3", score="90", sector="Bancos")],
        invested="19000",
        sectors={"Bancos": "9000"},
    )

    assert plan.allocations == ()
    assert _reasons(plan) == {"BANK3": Exclusion.SECTOR_LIMIT_REACHED}


def test_weights_are_measured_against_the_portfolio_with_the_money_in():
    plan = _plan([_candidate("AAAA3", score="90", held="1000")], invested="9000")

    (allocation,) = plan.allocations
    assert plan.base_value == Decimal(10000)
    assert allocation.weight_before == Decimal("0.10")
    assert allocation.weight_after == Decimal("0.14")


# -- an asset with no sector recorded ---------------------------------


def test_an_asset_without_a_sector_is_refused_by_default():
    """A ceiling that cannot be evaluated is not a ceiling.

    Funding it anyway would suspend the rule exactly where the data is
    thinnest, quietly favouring whichever assets nobody filled the field
    in for.
    """
    plan = _plan([_candidate("NOSEC3", score="90", sector=None)])

    assert plan.allocations == ()
    assert _reasons(plan) == {"NOSEC3": Exclusion.SECTOR_UNKNOWN}


def test_the_sector_requirement_can_be_switched_off(monkeypatch):
    """Rule 32: the investor's limits are theirs, including this one."""
    plan = _plan(
        [_candidate("NOSEC3", score="90", sector=None)],
        invested="19000",
        require_sector=False,
    )

    assert _amounts(plan) == {"NOSEC3": Decimal("400.00")}


# -- how one contribution is spread -----------------------------------


def test_no_single_asset_takes_more_than_its_share_of_one_contribution():
    """The asset ceiling barely binds at this size; this one does.

    R$ 1.000 into a R$ 20.000 portfolio could go entirely into one name
    and still leave it under 20%, so without a share cap the monthly
    decision would be all-or-nothing.
    """
    plan = _plan([_candidate("ONLY3", score="90")], invested="19000")

    (allocation,) = plan.allocations
    assert allocation.amount == Decimal("400.00")
    assert allocation.limited_by is Limit.POSITION_SHARE
    assert plan.unallocated == Decimal("600.00")


def test_the_number_of_positions_is_capped():
    """Six candidates, an empty portfolio: five slices of R$ 200 fit."""
    plan = _plan(
        [
            _candidate("AAAA3", score="95", sector="A"),
            _candidate("BBBB3", score="90", sector="B"),
            _candidate("CCCC3", score="85", sector="C"),
            _candidate("DDDD3", score="80", sector="D"),
            _candidate("EEEE3", score="75", sector="E"),
            _candidate("FFFF3", score="70", sector="F"),
        ]
    )

    assert len(plan.allocations) == 5
    assert _reasons(plan) == {"FFFF3": Exclusion.MAX_POSITIONS_REACHED}


def test_a_slice_below_the_minimum_ticket_is_not_emitted():
    """R$ 60 of headroom is more brokerage fee than investment."""
    plan = _plan(
        [_candidate("NEAR3", score="90", held="3940", sector="Energia")],
        invested="19000",
        sectors={"Energia": "3940"},
    )

    assert plan.allocations == ()
    assert _reasons(plan) == {"NEAR3": Exclusion.BELOW_MINIMUM_TICKET}
    assert plan.unallocated == CONTRIBUTION


def test_a_candidate_reached_with_too_little_money_left_says_so():
    plan = _plan(
        [
            _candidate("AAAA3", score="95", sector="A"),
            _candidate("BBBB3", score="90", sector="B"),
            _candidate("CCCC3", score="85", sector="C"),
        ],
        invested="19000",
        max_share_per_position=Decimal("0.49"),
    )

    assert _amounts(plan) == {"AAAA3": Decimal("490.00"), "BBBB3": Decimal("490.00")}
    assert _reasons(plan) == {"CCCC3": Exclusion.CONTRIBUTION_EXHAUSTED}


# -- money arithmetic --------------------------------------------------


def test_amounts_are_rounded_down_to_the_centavo():
    """Rounding up could push an allocation a centavo past a ceiling.

    A third of R$ 1.000 is R$ 333.333…; the residue lands in
    `unallocated`, where it is visible rather than absorbed.
    """
    plan = _plan(
        [_candidate("AAAA3", score="90")],
        invested="19000",
        max_share_per_position=Decimal(1) / Decimal(3),
    )

    (allocation,) = plan.allocations
    assert allocation.amount == Decimal("333.33")
    assert plan.unallocated == Decimal("666.67")


def test_a_non_positive_contribution_is_rejected():
    with pytest.raises(ValueError):
        _plan([_candidate("AAAA3")], contribution=Decimal(0))


# -- the empty portfolio ----------------------------------------------


def test_an_empty_portfolio_can_still_be_planned_for():
    """The first contribution, where the base is the contribution itself.

    Nothing is held, so the 20% ceiling is 20% of R$ 1.000 — and it is
    the ceiling that binds, not the per-position share. Refusing to put
    more than R$ 200 into one name is the right answer for someone
    starting from nothing: buy five things, not one.
    """
    plan = _plan([_candidate("AAAA3", score="90")], invested="0")

    (allocation,) = plan.allocations
    assert plan.base_value == CONTRIBUTION
    assert allocation.weight_before == Decimal(0)
    assert allocation.amount == Decimal("200.00")
    assert allocation.limited_by is Limit.ASSET_WEIGHT
    assert allocation.weight_after == MAX_ASSET_WEIGHT
    # Only one asset is tracked, so 80% of the contribution has nowhere
    # to go under the ceiling. Reported, not forced somewhere.
    assert plan.unallocated == Decimal("800.00")


def test_an_empty_universe_allocates_nothing():
    plan = _plan([])

    assert plan.allocations == ()
    assert plan.skipped == ()
    assert plan.unallocated == CONTRIBUTION


# -- the plan explains itself ------------------------------------------


def test_every_allocation_carries_the_pillars_it_rests_on():
    """Decomposable the way the score is (rule 30)."""
    plan = _plan([_candidate("AAAA3", score="90")], invested="19000")

    (allocation,) = plan.allocations
    assert [sub.name for sub in allocation.score.sub_scores] == ["risk", "growth"]
    assert allocation.headroom > allocation.amount
    assert allocation.rank == 1


def test_the_policy_travels_with_the_plan():
    """A plan is only interpretable next to the limits that produced it."""
    plan = _plan([_candidate("AAAA3")], max_positions=1)

    assert plan.policy.max_positions == 1
    assert plan.policy.max_asset_weight == MAX_ASSET_WEIGHT
