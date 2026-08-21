"""Where the portfolio should end up (roadmap §22, AGENTS.md rule 34).

Pure, deterministic and I/O-free, like `scoring.py` and `allocation.py`.
Same universe, same policy — same targets, forever (rule 113). Loading
lives in `service.py`.

Rule 34 asks for three numbers: `current_weight`, `target_weight` and
`weight_gap`. The first comes from the ledger and the third is a
subtraction. **The whole wave is the second one**, and the roadmap does
not say where it comes from.

## The target must not be a function of where the portfolio already is

The obvious construction is to make the target proportional to the
`final_score` the universe is already ranked by. It does not survive
contact with the number.

Measured on PETR4 against the real database, holding it from 0% to 20%:

| held | final_score | quality | valuation | growth | risk | diversification |
|------|-------------|---------|-----------|--------|------|-----------------|
|   0% |   **76.72** |    97.8 |      93.5 |   76.7 | 28.3 |           100.0 |
|   5% |       73.91 |    97.8 |      93.5 |   76.7 | 28.3 |            81.2 |
|  10% |       71.10 |    97.8 |      93.5 |   76.7 | 28.3 |            62.5 |
|  15% |       68.28 |    97.8 |      93.5 |   76.7 | 28.3 |            43.8 |
|  20% |   **65.47** |    97.8 |      93.5 |   76.7 | 28.3 |            25.0 |

Nothing about the company changed — the four merit pillars are constant
across the whole table. What fell is Diversification, the one pillar that
reads the holder rather than the asset.

A target built on that recedes as the portfolio approaches it. The
investor is told to close a 4 p.p. gap, closes two of them, and finds the
gap is now 1 p.p. because the act of buying lowered the target. The
number reported as a distance is not a distance to anything.

So the target is built from **merit** — Quality, Valuation, Growth and
Risk, recomposed on their own by `scoring.merit` — and never from
Diversification.

## Concentration does not disappear; it moves to where it cannot recurse

Dropping the pillar is not dropping the limit. Concentration comes back
as the **ceilings** that cap the targets, which are the very same
`max_asset_weight` and `max_sector_weight` the Diversification pillar
scores against, read from `AllocationPolicy` so the two cannot drift.

As a constraint it is stable in a way it is not as a term: a cap says
"no more than 20% here" whatever the portfolio holds today, while a
score term says "you are at 15%, so want less of this", which is the
recursion. Recorded in ADR-027.

## Targets are proportional to merit, which spreads them at most 2:1

Above the `min_score` floor of 50, merit runs 50–100, so the best asset
in a universe can carry at most twice the target of the worst one still
eligible. That ratio is a property worth keeping rather than an accident:
a conservative portfolio should not let a scoring formula calibrated on
five-ish indicators concentrate ten to one, and the ceilings then trim
whatever the proportion still overshoots.

## Coverage is measured over merit, which is stricter than the allocator

`allocation.py` tests `min_coverage` against `AssetScore.coverage`, the
fraction of all five pillars available. Diversification is essentially
never missing — an empty portfolio still has a weight of zero — so that
denominator carries a constant 0.15 that says nothing about how much is
known.

Merit coverage divides by the merit weights alone. Under the shared
`min_coverage` of 0.50 that asks for 0.425 of merit where the allocator
asks for 0.35, and the extra strictness is deliberate: the allocator has
coverage **tiers** as a second line of defence against comparing two
incomparable scores, and a target weight has none. It is a single number
handed to the investor as a destination.

The trap is live in this project's own database, not hypothetical: ITUB4
scores **92.47 on coverage 0.40** — the highest number in the universe,
assembled out of the only two pillars that never go missing.

## The targets need not add up to 1, and the remainder is reported

With one rateable asset and a 20% ceiling, the targets sum to 0.20 and
0.80 has no owner. Nothing is redistributed to make the total look
whole: that would quietly hand the remainder to whoever happened to be
rateable, which is the least-known corner of the universe. It comes back
as `unassigned`, the same way the allocator reports `unallocated`.

## Nothing is stored

A target is derived from the ledger, the scores and the policy, exactly
as positions and plans are (rule 16, ADR-002).
"""

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from enum import Enum

from app.domain.recommendations.allocation import (
    DEFAULT_POLICY,
    AllocationPolicy,
    Candidate,
    Exclusion,
    percent,
    round_score,
)
from app.domain.recommendations.scoring import (
    SCORING_FORMULA_VERSION,
    AssetScore,
    Merit,
    merit,
)

ZERO = Decimal(0)
ONE = Decimal(1)

#: Precision weights are reported to: 1e-6, or ten-thousandths of a
#: percentage point. Fine enough that quantisation never moves a status
#: across the band, coarse enough that a weight is readable.
WEIGHT_STEP = Decimal("0.000001")

#: Version of the target model: how merit becomes a weight, and the
#: ceilings that trim it.
#:
#: Separate from `SCORING_FORMULA_VERSION` and from
#: `ALLOCATION_RULES_VERSION` for the same reason those are separate from
#: each other — the three change for different reasons, and a set of
#: targets records all of them (rule 30).
TARGET_MODEL_VERSION = "1.0.0"


class DriftStatus(str, Enum):
    """Where a weight sits relative to its target, given the band."""

    UNDER = "UNDER"
    ON_TARGET = "ON_TARGET"
    OVER = "OVER"


class TargetLimit(str, Enum):
    """What decided a target weight.

    `MERIT` means nothing trimmed it — the asset got its proportional
    share. The others name the ceiling that did.
    """

    MERIT = "MERIT"
    ASSET_WEIGHT = "ASSET_WEIGHT"
    SECTOR_WEIGHT = "SECTOR_WEIGHT"
    PORTFOLIO_FULL = "PORTFOLIO_FULL"


@dataclass(frozen=True)
class AssetTarget:
    """One row of the drift table: an asset, where it is, where it goes.

    Every asset offered gets a row, including the ones with no target:
    an asset the investor holds and the model cannot rate is exactly the
    row that must not go missing, and its `excluded` names why.

    `weight_gap` is `target_weight - current_weight` as a fraction, so
    0.04 is the +4 p.p. of rule 34's example. Positive means underweight.
    """

    ticker: str
    asset_id: int
    name: str
    sector: str | None
    merit_score: Decimal | None
    merit_coverage: Decimal
    #: Cost basis held in this asset, in BRL. Carried alongside
    #: `current_weight` rather than recovered from it: the weight is
    #: quantised for reading, and a plan that has to turn a target back
    #: into money must not do it through a rounded fraction.
    held_amount: Decimal
    current_weight: Decimal
    target_weight: Decimal
    weight_gap: Decimal
    status: DriftStatus
    #: `None` for an excluded asset: nothing trimmed its target, it never
    #: had one.
    limited_by: TargetLimit | None
    excluded: Exclusion | None
    detail: str
    score: AssetScore


@dataclass(frozen=True)
class PortfolioTargets:
    """The full drift table, decomposable the way a score is.

    `assigned + unassigned == 1` always. `underweight_gap` and
    `overweight_gap` are reported separately rather than netted into one
    "drift" figure, because they are closed by different actions — one by
    contributing, the other only by selling or by dilution — and a single
    number would hide which.
    """

    model_version: str
    formula_version: str
    policy: AllocationPolicy
    #: Portfolio cost basis the current weights are measured against.
    invested: Decimal
    targets: tuple[AssetTarget, ...]
    assigned: Decimal
    unassigned: Decimal
    underweight_gap: Decimal
    overweight_gap: Decimal
    #: Weight held in assets that were not offered as candidates — a
    #: delisted or deactivated holding still counts in `invested`, and
    #: without this the table's own weights would not add up.
    untracked_weight: Decimal


def compute_targets(
    candidates: list[Candidate],
    invested: Decimal,
    policy: AllocationPolicy = DEFAULT_POLICY,
) -> PortfolioTargets:
    """Target weight, current weight and gap for every candidate.

    `invested` is the portfolio's total cost basis, the denominator of
    the current weights. It is passed in rather than summed from
    `candidates` because the portfolio can hold an asset the universe no
    longer offers, and that money is still part of the whole.

    Candidates may arrive in any order; the result does not depend on it.
    Rows come back most-underweight first — which is rule 34's priority
    order — with the ticker breaking ties so it is total (rule 113).
    """
    rateable: list[tuple[Candidate, Merit]] = []
    excluded: list[tuple[Candidate, Merit, Exclusion, str]] = []
    for candidate in candidates:
        assessment = merit(candidate.score)
        reason = _ineligibility(candidate, assessment, policy)
        if reason is None:
            rateable.append((candidate, assessment))
        else:
            excluded.append((candidate, assessment, *reason))

    weights = _fill(rateable, policy)

    rows = [
        _row(candidate, assessment, *weights[candidate.ticker], invested, policy)
        for candidate, assessment in rateable
    ] + [
        _excluded_row(candidate, assessment, reason, detail, invested, policy)
        for candidate, assessment, reason, detail in excluded
    ]
    rows.sort(key=lambda row: (-row.weight_gap, row.ticker))

    assigned = sum((row.target_weight for row in rows), ZERO)
    held = sum((row.current_weight for row in rows), ZERO)
    return PortfolioTargets(
        model_version=TARGET_MODEL_VERSION,
        formula_version=SCORING_FORMULA_VERSION,
        policy=policy,
        invested=invested,
        targets=tuple(rows),
        assigned=assigned,
        unassigned=ONE - assigned,
        underweight_gap=sum((max(row.weight_gap, ZERO) for row in rows), ZERO),
        overweight_gap=sum((max(-row.weight_gap, ZERO) for row in rows), ZERO),
        # Nothing is held at all when there is no cost basis, so there is
        # nothing untracked either — the alternative reads as "100% of
        # your portfolio is somewhere we cannot see", about a portfolio
        # that is empty.
        untracked_weight=(ONE - held if invested > 0 else ZERO),
    )


# -- the fill --------------------------------------------------------


def _fill(
    rateable: list[tuple[Candidate, Merit]], policy: AllocationPolicy
) -> dict[str, tuple[Decimal, TargetLimit]]:
    """Spread one whole portfolio across the rateable assets by merit.

    Water-filling: distribute what is left of the portfolio in
    proportion to merit, freeze whichever ceiling that first breaches,
    and distribute again over what is still free. One constraint is
    frozen per pass, so the loop ends — `free` strictly shrinks.

    Freezing rather than one-shot capping is what keeps the total right.
    Capping in place would leave the trimmed weight unassigned even when
    another asset had room for it; here that weight returns to the
    budget and is offered to whoever is still free.
    """
    merits = {candidate.ticker: assessment.value for candidate, assessment in rateable}
    sectors = {candidate.ticker: candidate.sector for candidate, _ in rateable}
    frozen: dict[str, tuple[Decimal, TargetLimit]] = {}
    free = set(merits)

    while free:
        budget = ONE - sum((weight for weight, _ in frozen.values()), ZERO)
        if budget <= 0:  # pragma: no cover - guards an invariant
            # Unreachable, and kept because the reason it is unreachable
            # is an invariant of the fill rather than of the inputs:
            # every freeze takes *no more* than the asset's provisional
            # share, so the budget can only reach zero on the pass that
            # empties `free`. Should a future ceiling break that, the
            # remainder is a target of zero and says so, rather than the
            # loop running on a negative budget.
            frozen.update(
                (ticker, (ZERO, TargetLimit.PORTFOLIO_FULL)) for ticker in free
            )
            break

        # `_ineligibility` rejected a None merit already; the `or ZERO`
        # keeps the type checker honest.
        total = sum((merits[ticker] or ZERO for ticker in free), ZERO)
        if total <= 0:
            frozen.update((ticker, (ZERO, TargetLimit.MERIT)) for ticker in free)
            break
        share = {ticker: budget * (merits[ticker] or ZERO) / total for ticker in free}

        # The sector ceiling is tested **first**, and the order is not
        # cosmetic. Freezing an asset at the per-asset ceiling without
        # asking its sector first lets three names in one sector settle
        # at 20% each and put the sector at 60%, past a 40% limit that
        # was never consulted. Going the other way is safe, because the
        # per-asset ceiling gets its second pass inside the sector's own
        # room below.
        breach = _breached_sector(free, share, sectors, frozen, policy)
        if breach is not None:
            room, members = breach
            if room <= 0:
                frozen.update(
                    (ticker, (ZERO, TargetLimit.SECTOR_WEIGHT)) for ticker in members
                )
                free -= set(members)
                continue
            weight_in_sector = sum((merits[t] or ZERO for t in members), ZERO)
            within = {
                ticker: room * (merits[ticker] or ZERO) / weight_in_sector
                for ticker in members
            }
            # A sector's room can still be more than one asset may hold,
            # so the per-asset ceiling gets another pass before the
            # sector is settled.
            over_inside = [
                ticker for ticker in members if within[ticker] > policy.max_asset_weight
            ]
            if over_inside:
                ticker = max(over_inside, key=lambda item: (within[item], item))
                frozen[ticker] = (policy.max_asset_weight, TargetLimit.ASSET_WEIGHT)
                free.discard(ticker)
                continue
            frozen.update(
                (ticker, (within[ticker], TargetLimit.SECTOR_WEIGHT))
                for ticker in members
            )
            free -= set(members)
            continue

        over_asset = [
            ticker for ticker in free if share[ticker] > policy.max_asset_weight
        ]
        if over_asset:
            # Every one of these ends at the ceiling whatever the order,
            # so freezing them one at a time costs a pass and buys
            # determinism for free.
            ticker = max(over_asset, key=lambda item: (share[item], item))
            frozen[ticker] = (policy.max_asset_weight, TargetLimit.ASSET_WEIGHT)
            free.discard(ticker)
            continue

        frozen.update((ticker, (share[ticker], TargetLimit.MERIT)) for ticker in free)
        break

    return frozen


def _breached_sector(
    free: set[str],
    share: dict[str, Decimal],
    sectors: dict[str, str | None],
    frozen: dict[str, tuple[Decimal, TargetLimit]],
    policy: AllocationPolicy,
) -> tuple[Decimal, list[str]] | None:
    """How much room the first over-claiming sector has, and for whom.

    Sectors are visited in name order, so which breach is settled first
    — and therefore the whole result, since settling one changes the
    budget for the rest — does not depend on dictionary ordering.

    An asset with no sector recorded has no sector ceiling to breach.
    That only arises under `require_sector=False`; the default refuses
    such an asset outright, because a ceiling that cannot be evaluated is
    not a ceiling.
    """
    members: dict[str, list[str]] = {}
    for ticker in free:
        sector = sectors[ticker]
        if sector is not None:
            members.setdefault(sector, []).append(ticker)

    for sector in sorted(members):
        settled = sum(
            (
                weight
                for ticker, (weight, _) in frozen.items()
                if sectors[ticker] == sector
            ),
            ZERO,
        )
        room = policy.max_sector_weight - settled
        claim = sum((share[ticker] for ticker in members[sector]), ZERO)
        if claim > room:
            return room, sorted(members[sector])
    return None


# -- rows ------------------------------------------------------------


def _row(
    candidate: Candidate,
    assessment: Merit,
    target: Decimal,
    limited_by: TargetLimit,
    invested: Decimal,
    policy: AllocationPolicy,
) -> AssetTarget:
    current = _current_weight(candidate, invested)
    target = _floor_weight(target)
    return AssetTarget(
        ticker=candidate.ticker,
        asset_id=candidate.asset_id,
        name=candidate.name,
        sector=candidate.sector,
        merit_score=assessment.value,
        merit_coverage=assessment.coverage,
        held_amount=candidate.held_amount,
        current_weight=current,
        target_weight=target,
        weight_gap=target - current,
        status=_status(target - current, policy),
        limited_by=limited_by,
        excluded=None,
        detail=_reached(limited_by, target, policy),
        score=candidate.score,
    )


def _excluded_row(
    candidate: Candidate,
    assessment: Merit,
    reason: Exclusion,
    detail: str,
    invested: Decimal,
    policy: AllocationPolicy,
) -> AssetTarget:
    """A candidate with no target, and what it is holding anyway.

    The target is zero and the gap is therefore minus whatever is held.
    That reads as "sell it", and it is deliberately not: no plan in this
    project sells (see `rebalancing.py`). It is the honest arithmetic of
    a position the model declines to endorse, and a portfolio taking
    monthly contributions closes it by dilution.
    """
    current = _current_weight(candidate, invested)
    return AssetTarget(
        ticker=candidate.ticker,
        asset_id=candidate.asset_id,
        name=candidate.name,
        sector=candidate.sector,
        merit_score=assessment.value,
        merit_coverage=assessment.coverage,
        held_amount=candidate.held_amount,
        current_weight=current,
        target_weight=ZERO,
        weight_gap=-current,
        status=_status(-current, policy),
        limited_by=None,
        excluded=reason,
        detail=detail,
        score=candidate.score,
    )


def _ineligibility(
    candidate: Candidate, assessment: Merit, policy: AllocationPolicy
) -> tuple[Exclusion, str] | None:
    """Why this candidate gets no target.

    The same four verdicts `allocation.ineligibility` reaches, tested
    against **merit** instead of the final score. Not a copy that drifted:
    testing `final_score` here would smuggle the Diversification pillar
    back into the target through the eligibility gate, so that an asset
    could lose its target precisely by being bought — which is the
    circularity this module exists to remove.
    """
    if assessment.value is None:
        return (
            Exclusion.NO_MERIT_SCORE,
            (
                "No merit score: fewer than two of Quality, Valuation, "
                "Growth and Risk were available."
            ),
        )
    if assessment.coverage < policy.min_coverage:
        return (
            Exclusion.COVERAGE_BELOW_MINIMUM,
            (
                f"Merit rests on {percent(assessment.coverage)} of its "
                f"pillars, below the {percent(policy.min_coverage)} minimum."
            ),
        )
    if assessment.value < policy.min_score:
        return (
            Exclusion.SCORE_BELOW_MINIMUM,
            (
                f"Merit of {round_score(assessment.value)}, below the "
                f"{round_score(policy.min_score)} minimum."
            ),
        )
    if policy.require_sector and candidate.sector is None:
        return (
            Exclusion.SECTOR_UNKNOWN,
            "No sector recorded, so the sector ceiling cannot be applied.",
        )
    return None


# -- helpers ---------------------------------------------------------


def _current_weight(candidate: Candidate, invested: Decimal) -> Decimal:
    """Share of the portfolio this asset is, at cost basis.

    Zero for an empty portfolio rather than undefined: holding nothing
    of everything is a real state, and it is the state every portfolio
    starts in.
    """
    if invested <= 0:
        return ZERO
    return (candidate.held_amount / invested).quantize(
        WEIGHT_STEP, rounding=ROUND_HALF_EVEN
    )


def _status(gap: Decimal, policy: AllocationPolicy) -> DriftStatus:
    if gap > policy.rebalance_band:
        return DriftStatus.UNDER
    if gap < -policy.rebalance_band:
        return DriftStatus.OVER
    return DriftStatus.ON_TARGET


def _reached(limited_by: TargetLimit, target: Decimal, policy: AllocationPolicy) -> str:
    if limited_by is TargetLimit.ASSET_WEIGHT:
        return (
            f"Merit alone would have targeted more; trimmed to the "
            f"{percent(policy.max_asset_weight)} per-asset ceiling."
        )
    if limited_by is TargetLimit.SECTOR_WEIGHT:
        return (
            f"Trimmed to this asset's share of the "
            f"{percent(policy.max_sector_weight)} sector ceiling."
        )
    if limited_by is TargetLimit.PORTFOLIO_FULL:
        return "The ceilings already account for the whole portfolio."
    return f"Merit's proportional share of the portfolio: {percent(target)}."


def _floor_weight(value: Decimal) -> Decimal:
    """A weight, rounded **down**.

    Down, never nearest, for the reason `floor_to_centavo` gives about
    money: rounding up could put a target a hair past a ceiling, and a
    target that violates its own limit in the last decimal still violates
    it. The residue lands in `unassigned`, where it is visible.
    """
    return value.quantize(WEIGHT_STEP, rounding=ROUND_DOWN)
