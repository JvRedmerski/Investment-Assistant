"""Tests for the target-weight model.

Pure function, hand-computed expectations (AGENTS.md rule 68). Every
weight below was worked out from the merits and the ceilings — the merit
share of the budget, or the ceiling that trimmed it — rather than read
back from a first run.

`_score` goes through the real `compose`, so `final_score` and `coverage`
are the genuine article: the point of several of these tests is precisely
that merit and the final score disagree, and a hand-built `AssetScore`
could not show that.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from app.domain.recommendations.allocation import (
    DEFAULT_POLICY,
    Candidate,
    Exclusion,
)
from app.domain.recommendations.scoring import (
    PILLAR_WEIGHTS,
    AssetScore,
    SubScore,
    compose,
    merit,
)
from app.domain.recommendations.targets import (
    DriftStatus,
    TargetLimit,
    compute_targets,
)

#: No ceilings and no floor: the shape of the fill on its own.
UNCONSTRAINED = replace(
    DEFAULT_POLICY,
    max_asset_weight=Decimal(1),
    max_sector_weight=Decimal(1),
    min_score=Decimal(0),
)


def _score(
    quality: str | None = None,
    valuation: str | None = None,
    growth: str | None = None,
    risk: str | None = None,
    diversification: str | None = "100",
) -> AssetScore:
    """An `AssetScore` with the named pillars available and the rest not."""
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


def _flat(value: str, diversification: str = "100") -> AssetScore:
    """A score whose four merit pillars all read `value`, so merit is it."""
    return _score(value, value, value, value, diversification)


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


def _by_ticker(targets) -> dict:
    return {row.ticker: row for row in targets.targets}


# -- merit -----------------------------------------------------------


def test_merit_ignores_the_pillar_that_reads_the_portfolio():
    """The whole reason the target is not built on `final_score`.

    Same company, two portfolios. The final score moves by 15 points;
    merit does not move at all.
    """
    empty = _score("80", "60", "40", "100", diversification="100")
    concentrated = _score("80", "60", "40", "100", diversification="0")

    # (0.25*80 + 0.20*60 + 0.15*40 + 0.25*100) = 63, over 1.00 of weight
    # once Diversification is there, so 63 + 0.15*100 = 78 against 63.
    assert empty.final_score == Decimal(78)
    assert concentrated.final_score == Decimal(63)

    # 63 over the 0.85 of merit weight that exists.
    expected = Decimal(63) / Decimal("0.85")
    assert merit(empty).value == expected
    assert merit(concentrated).value == expected
    assert merit(empty).coverage == Decimal(1)


def test_merit_renormalises_over_the_pillars_that_exist():
    """A missing pillar shrinks the denominator, it does not score zero."""
    assessment = merit(_score(quality="80", risk="40"))

    # (0.25*80 + 0.25*40) / 0.50
    assert assessment.value == Decimal(60)
    # 0.50 of the 0.85 that merit could have had.
    assert assessment.coverage == Decimal("0.50") / Decimal("0.85")


def test_merit_is_absent_below_two_pillars_even_when_a_score_exists():
    """`compose` counts Diversification; merit does not, and says so."""
    score = _score(risk="30")

    # Risk plus Diversification is two pillars, so there is a score.
    assert score.final_score is not None
    assessment = merit(score)
    assert assessment.value is None
    assert assessment.coverage == Decimal("0.25") / Decimal("0.85")


# -- the fill --------------------------------------------------------


def test_targets_are_proportional_to_merit_when_nothing_binds():
    targets = compute_targets(
        [
            _candidate("AAAA3", _flat("75")),
            _candidate("BBBB3", _flat("25"), sector="Bancos"),
        ],
        invested=Decimal(0),
        policy=UNCONSTRAINED,
    )

    rows = _by_ticker(targets)
    assert rows["AAAA3"].target_weight == Decimal("0.750000")
    assert rows["BBBB3"].target_weight == Decimal("0.250000")
    assert rows["AAAA3"].limited_by is TargetLimit.MERIT
    assert targets.assigned == Decimal(1)
    assert targets.unassigned == Decimal(0)


def test_the_asset_ceiling_redistributes_rather_than_discards():
    """What a ceiling trims goes back to whoever still has room.

    One asset at merit 100 and five at merit 50, each in its own sector.
    Raw shares are 100/350 = 28.57% and 50/350 = 14.29%; the first
    breaches the 20% ceiling. Capping in place would leave 8.57% of the
    portfolio unassigned. Refilling hands it to the other five, which go
    from 14.29% to 0.80 * 50/250 = 16%.
    """
    candidates = [_candidate("AAAA3", _flat("100"), sector="Energia")] + [
        _candidate(f"{letter * 4}3", _flat("50"), sector=letter) for letter in "BCDEF"
    ]

    targets = compute_targets(candidates, invested=Decimal(0))

    rows = _by_ticker(targets)
    assert rows["AAAA3"].target_weight == Decimal("0.200000")
    assert rows["AAAA3"].limited_by is TargetLimit.ASSET_WEIGHT
    for letter in "BCDEF":
        row = rows[f"{letter * 4}3"]
        assert row.target_weight == Decimal("0.160000")
        assert row.limited_by is TargetLimit.MERIT
    assert targets.assigned == Decimal(1)
    assert targets.unassigned == Decimal(0)


def test_the_sector_ceiling_is_shared_by_its_members():
    """Three names in one sector split its 40%, they do not each get it.

    Six assets of equal merit want one sixth each; the three in Bancos
    claim 50% of the portfolio between them and are cut to 40%/3 each.
    The 10% that frees up goes to the other three, which reach the 20%
    per-asset ceiling exactly without breaching it.
    """
    candidates = [
        _candidate(f"{letter * 4}3", _flat("100"), sector="Bancos") for letter in "ABC"
    ] + [_candidate(f"{letter * 4}3", _flat("100"), sector=letter) for letter in "DEF"]

    targets = compute_targets(candidates, invested=Decimal(0))

    rows = _by_ticker(targets)
    for letter in "ABC":
        row = rows[f"{letter * 4}3"]
        assert row.target_weight == Decimal("0.133333")
        assert row.limited_by is TargetLimit.SECTOR_WEIGHT
    for letter in "DEF":
        row = rows[f"{letter * 4}3"]
        assert row.target_weight == Decimal("0.200000")
        assert row.limited_by is TargetLimit.MERIT

    # 3 * 0.133333 is a thousandth of a percentage point short of 0.40,
    # because a target is floored rather than rounded. The residue is
    # reported, not absorbed.
    assert targets.assigned == Decimal("0.999999")
    assert targets.unassigned == Decimal("0.000001")


def test_the_sector_ceiling_is_tested_before_the_asset_ceiling():
    """Otherwise a sector can be filled 20% at a time past its own limit.

    Three assets in one sector and one outside it. Freezing on the
    per-asset ceiling first would settle all three of the first sector at
    20%, putting it at 60% against a 40% limit that was never consulted.
    """
    candidates = [
        _candidate("AAAA3", _flat("100"), sector="Bancos"),
        _candidate("BBBB3", _flat("100"), sector="Bancos"),
        _candidate("CCCC3", _flat("50"), sector="Bancos"),
        _candidate("DDDD3", _flat("50"), sector="Energia"),
    ]

    targets = compute_targets(candidates, invested=Decimal(0))

    rows = _by_ticker(targets)
    # 0.40 shared out over merits 100/100/50.
    assert rows["AAAA3"].target_weight == Decimal("0.160000")
    assert rows["BBBB3"].target_weight == Decimal("0.160000")
    assert rows["CCCC3"].target_weight == Decimal("0.080000")
    in_sector = sum(rows[t].target_weight for t in ("AAAA3", "BBBB3", "CCCC3"))
    assert in_sector == DEFAULT_POLICY.max_sector_weight

    # The one outside would take the whole remaining 60%; its own
    # ceiling, not its sector's, is what stops it at 20%.
    assert rows["DDDD3"].target_weight == Decimal("0.200000")
    assert rows["DDDD3"].limited_by is TargetLimit.ASSET_WEIGHT
    assert targets.assigned == Decimal("0.600000")
    assert targets.unassigned == Decimal("0.400000")


def test_one_rateable_asset_leaves_the_rest_unassigned():
    """The shape of the real database, and the answer must not be 100%.

    A lone rateable asset is capped at 20% and the other 80% has no
    owner. Handing it to the only name that could be scored is exactly
    the concentration the ceiling exists to prevent.
    """
    targets = compute_targets(
        [_candidate("PETR4", _flat("76"), sector="Energia")],
        invested=Decimal(0),
    )

    row = _by_ticker(targets)["PETR4"]
    assert row.target_weight == Decimal("0.200000")
    assert row.limited_by is TargetLimit.ASSET_WEIGHT
    assert targets.assigned == Decimal("0.200000")
    assert targets.unassigned == Decimal("0.800000")


def test_merit_of_zero_targets_zero():
    targets = compute_targets(
        [_candidate("AAAA3", _flat("0")), _candidate("BBBB3", _flat("0"))],
        invested=Decimal(0),
        policy=replace(UNCONSTRAINED, min_score=Decimal(0)),
    )

    assert all(row.target_weight == Decimal(0) for row in targets.targets)
    assert targets.assigned == Decimal(0)
    assert targets.unassigned == Decimal(1)


def test_no_candidates_assigns_nothing():
    targets = compute_targets([], invested=Decimal(0))

    assert targets.targets == ()
    assert targets.unassigned == Decimal(1)
    assert targets.untracked_weight == Decimal(0)


# -- current, target, gap (rule 34) ----------------------------------


@pytest.fixture
def drifted():
    """Five equal-merit assets at 20% each, held at five different weights."""
    held = {
        "AAAA3": "100",
        "BBBB3": "250",
        "CCCC3": "190",
        "DDDD3": "210",
        "EEEE3": "250",
    }
    return compute_targets(
        [
            _candidate(ticker, _flat("80"), sector=ticker[0], held=amount)
            for ticker, amount in held.items()
        ],
        invested=Decimal(1000),
    )


def test_gap_is_target_minus_current(drifted):
    rows = _by_ticker(drifted)

    assert rows["AAAA3"].current_weight == Decimal("0.100000")
    assert rows["AAAA3"].target_weight == Decimal("0.200000")
    assert rows["AAAA3"].weight_gap == Decimal("0.100000")

    assert rows["BBBB3"].current_weight == Decimal("0.250000")
    assert rows["BBBB3"].weight_gap == Decimal("-0.050000")


def test_status_uses_the_band(drifted):
    rows = _by_ticker(drifted)

    assert rows["AAAA3"].status is DriftStatus.UNDER  # +10 p.p.
    assert rows["BBBB3"].status is DriftStatus.OVER  # -5 p.p.
    assert rows["CCCC3"].status is DriftStatus.ON_TARGET  # +1 p.p.
    assert rows["DDDD3"].status is DriftStatus.ON_TARGET  # -1 p.p.
    assert rows["EEEE3"].status is DriftStatus.OVER  # -5 p.p.


def test_a_narrower_band_makes_the_same_portfolio_off_target(drifted):
    """The band is a policy knob, not a constant of nature (rule 32)."""
    narrow = compute_targets(
        [
            _candidate(row.ticker, row.score, sector=row.sector, held="190")
            for row in drifted.targets
            if row.ticker == "CCCC3"
        ],
        invested=Decimal(1000),
        policy=replace(DEFAULT_POLICY, rebalance_band=Decimal("0.005")),
    )

    # 19% held against a 20% target: inside a 2 p.p. band, outside a
    # half-point one.
    assert _by_ticker(narrow)["CCCC3"].status is DriftStatus.UNDER


def test_the_two_gaps_are_reported_separately(drifted):
    """Netting them would hide which one contributing can actually close.

    Every row counts, including the two inside the band: the band
    decides whether a gap is worth *acting* on, and the totals measure
    how far the portfolio is, which is a different question. Here
    +10 and +1 against -1, -5 and -5.
    """
    assert drifted.underweight_gap == Decimal("0.110000")
    assert drifted.overweight_gap == Decimal("0.110000")


def test_rows_come_back_most_underweight_first(drifted):
    """Rule 34's priority order, with the ticker breaking ties."""
    assert [row.ticker for row in drifted.targets] == [
        "AAAA3",  # +10 p.p.
        "CCCC3",  # +1 p.p.
        "DDDD3",  # -1 p.p.
        "BBBB3",  # -5 p.p.
        "EEEE3",  # -5 p.p.
    ]


def test_order_of_candidates_does_not_change_the_result(drifted):
    """Rule 113: the same inputs give the same targets, every run."""
    shuffled = compute_targets(
        [
            _candidate(
                row.ticker,
                row.score,
                sector=row.sector,
                held=str(row.current_weight * 1000),
            )
            for row in reversed(drifted.targets)
        ],
        invested=Decimal(1000),
    )

    assert [row.ticker for row in shuffled.targets] == [
        row.ticker for row in drifted.targets
    ]
    assert [row.target_weight for row in shuffled.targets] == [
        row.target_weight for row in drifted.targets
    ]


# -- what gets no target ---------------------------------------------


def test_a_held_asset_with_no_merit_still_gets_a_row():
    """The row that must not go missing.

    Risk alone gives a final score — Diversification is the second
    pillar — and no merit at all. Dropping the asset would hide 20% of
    the portfolio from the table that is meant to explain it.
    """
    targets = compute_targets(
        [_candidate("XXXX3", _score(risk="30"), held="200")],
        invested=Decimal(1000),
    )

    row = _by_ticker(targets)["XXXX3"]
    assert row.excluded is Exclusion.NO_MERIT_SCORE
    assert row.merit_score is None
    assert row.target_weight == Decimal(0)
    assert row.current_weight == Decimal("0.200000")
    assert row.weight_gap == Decimal("-0.200000")
    assert row.status is DriftStatus.OVER
    assert row.limited_by is None


def test_merit_coverage_below_the_minimum_is_excluded():
    """Valuation plus Growth is 0.35 of 0.85, under the 0.50 floor."""
    targets = compute_targets(
        [_candidate("XXXX3", _score(valuation="90", growth="90"))],
        invested=Decimal(0),
    )

    row = _by_ticker(targets)["XXXX3"]
    assert row.excluded is Exclusion.COVERAGE_BELOW_MINIMUM
    assert row.merit_score == Decimal(90)
    assert row.target_weight == Decimal(0)


def test_merit_below_the_minimum_is_excluded():
    targets = compute_targets([_candidate("XXXX3", _flat("40"))], invested=Decimal(0))

    row = _by_ticker(targets)["XXXX3"]
    assert row.excluded is Exclusion.SCORE_BELOW_MINIMUM
    assert "40.0" in row.detail


def test_eligibility_reads_merit_and_not_the_final_score():
    """Otherwise concentration would come back through the gate.

    Quality 100 and Risk 0 is a merit of 50, which clears the floor.
    Held at the ceiling, Diversification drags the final score to 41.2,
    below the same floor — and the asset would lose its target for the
    sole reason that it had been bought.
    """
    score = _flat("50", diversification="0")
    concentrated = _score("100", None, None, "0", diversification="0")

    assert merit(concentrated).value == Decimal(50)
    assert concentrated.final_score < DEFAULT_POLICY.min_score

    targets = compute_targets([_candidate("XXXX3", concentrated)], Decimal(0))
    assert _by_ticker(targets)["XXXX3"].excluded is None
    assert merit(score).value == Decimal(50)


def test_an_asset_with_no_sector_is_refused_by_default():
    targets = compute_targets(
        [_candidate("XXXX3", _flat("80"), sector=None)], invested=Decimal(0)
    )

    assert _by_ticker(targets)["XXXX3"].excluded is Exclusion.SECTOR_UNKNOWN


def test_an_asset_with_no_sector_is_targeted_when_the_policy_allows_it():
    targets = compute_targets(
        [_candidate("XXXX3", _flat("80"), sector=None)],
        invested=Decimal(0),
        policy=replace(DEFAULT_POLICY, require_sector=False),
    )

    row = _by_ticker(targets)["XXXX3"]
    assert row.excluded is None
    assert row.target_weight == Decimal("0.200000")
    assert row.limited_by is TargetLimit.ASSET_WEIGHT


# -- the denominator -------------------------------------------------


def test_untracked_weight_names_the_hole():
    """Money in a holding nobody offered still counts in the whole."""
    targets = compute_targets(
        [_candidate("AAAA3", _flat("80"), held="800")],
        invested=Decimal(1000),
    )

    assert _by_ticker(targets)["AAAA3"].current_weight == Decimal("0.800000")
    assert targets.untracked_weight == Decimal("0.200000")


def test_an_empty_portfolio_has_nothing_untracked():
    """Zero, not 100%: nothing is held, so nothing is unaccounted for."""
    targets = compute_targets([_candidate("AAAA3", _flat("80"))], invested=Decimal(0))

    assert _by_ticker(targets)["AAAA3"].current_weight == Decimal(0)
    assert targets.untracked_weight == Decimal(0)


def test_versions_are_reported():
    """Rule 30: a set of targets is traceable to the rules that made it."""
    targets = compute_targets([], invested=Decimal(0))

    assert targets.model_version == "1.0.0"
    assert targets.formula_version
