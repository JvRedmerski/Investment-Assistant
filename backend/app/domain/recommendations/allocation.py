"""Where the next contribution goes (roadmap §21, AGENTS.md rules 31/32/33).

Pure, deterministic and I/O-free, like `scoring.py`. Same portfolio, same
universe, same policy — same plan, forever (rule 113). Loading lives in
`service.py`.

This module **combines**; it never recalculates. Scores arrive already
composed, and nothing here reaches back into a pillar to adjust it.

## The question is not "which asset scores highest"

Rule 31 states the product's question as *"qual novo aporte melhora minha
carteira atual?"* and explicitly not *"qual ativo tem maior score?"*. The
score already answers the first half — Diversification reads the
portfolio's concentration, so an asset the investor is already heavy in
scores lower. This module answers the second half: how much money, into
which of them, without breaking the limits the profile sets.

## `coverage` is where a ranking quietly goes wrong

Two scores with different coverage are **not comparable**, even though
both are numbers between 0 and 100 (see `scoring.py`). Sorting the
universe by `final_score` and paying out from the top ignores that, and
it does not fail randomly — it fails in one direction.

The pillars that go missing are the fundamentals ones, and the pillar
that survives every gap is Diversification, which scores near 100 for
anything the portfolio does not already hold. An asset with no filings
therefore arrives carrying a high score built out of the two pillars that
were never in doubt. Rank on that and the least-known assets win.

So the plan does two things about it, and says which:

1. **A floor.** Below `min_coverage` an asset is not a candidate at all.
   A score resting on a third of the formula is mostly a description of
   what is missing.
2. **Tiers.** Above the floor, candidates are grouped into coverage
   bands `coverage_tier_width` wide, and a higher band always outranks a
   lower one. Score decides the order *within* a band, where it is
   comparing like with like, and never across bands.

A lower tier is still funded, but only with what the tier above it could
not absorb. That keeps the money working without ever putting two
incomparable numbers side by side.

## "Conservative" is arithmetic, not an adjective

Rule 32 asks for concentration and volatility handled as quantitative
restrictions, with the exact weights **configurable** — an investor's
limits are theirs, not a constant of nature. `AllocationPolicy` carries
every one of them, and the defaults are named constants below.

The per-asset and per-sector ceilings are taken **from the scoring
scales**, not written out again here. They are the same limits the
Diversification pillar scores against, and a second copy would be free to
drift until an asset could be scored good for diversifying into a
position the allocator refuses to fund.

Risk is not re-tested here either: it is a quarter of the score already,
calibrated for a conservative profile, so an asset that swings hard has
been priced down before it reaches this module.

## Weights are measured against the portfolio after the contribution

The base is `invested + contribution`: the portfolio as it stands once
the money has been put in. Anything the limits leave unplaced is reported
as `unallocated` and stays in the base as cash, which is what it is — so
the weights in the plan are the weights the investor will actually have,
not the weights of a portfolio that spent everything.

Amounts are cost basis, the same measure `PortfolioExposure` uses for the
Diversification pillar. Market value is the more faithful reading of
current exposure and it is deliberately not used, for the reason recorded
in `service.py`: it would make the whole calculation absent whenever one
held asset is missing a stored price.

## Nothing is stored

A plan is derived, never persisted — the same rule positions follow
(rule 16, ADR-002). It is a function of the ledger, the scores and the
policy, all of which are already stored, and freezing a copy would create
a second version of the truth that ages. The `recommendations` table
remains unused.
"""

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import Enum

from app.domain.recommendations.scoring import (
    ASSET_WEIGHT_SCALE,
    SCORING_FORMULA_VERSION,
    SECTOR_WEIGHT_SCALE,
    AssetScore,
)

ZERO = Decimal(0)
CENTAVO = Decimal("0.01")

#: Version of the allocation rules: the policy defaults and the ranking.
#:
#: Separate from `SCORING_FORMULA_VERSION` because the two change for
#: different reasons — a plan records both, so it can always be traced to
#: the scores it consumed *and* the rules it applied (rule 30).
ALLOCATION_RULES_VERSION = "1.0.0"

# -- concentration ceilings (rule 32) --------------------------------
#
# Read off the Diversification scales rather than restated, so the
# allocator's limits and the score's cannot disagree. `at_zero` is the
# weight at which that pillar scores zero, which is precisely the point
# the portfolio should stop adding.

MAX_ASSET_WEIGHT = ASSET_WEIGHT_SCALE.at_zero
MAX_SECTOR_WEIGHT = SECTOR_WEIGHT_SCALE.at_zero

# -- how one contribution may be spread ------------------------------

#: Most of a single contribution any one asset may take.
#:
#: A separate limit from `MAX_ASSET_WEIGHT`, and needed because that one
#: stops binding as the portfolio grows: a R$ 1.000 contribution into a
#: R$ 20.000 portfolio can go entirely into one name and still leave it
#: under 20%. Without this the monthly decision would be all-or-nothing,
#: and a single bad month would land undiluted.
#:
#: The two swap places by portfolio size. Early on the 20% ceiling is the
#: tighter of the two and this one never applies; past roughly
#: `contribution / (MAX_ASSET_WEIGHT - MAX_SHARE_PER_POSITION)` it is the
#: only one left holding.
MAX_SHARE_PER_POSITION = Decimal("0.40")

#: How many assets one contribution may be split across.
#:
#: Five, which is `1 / MAX_ASSET_WEIGHT` and not a coincidence. A
#: portfolio at the 20% ceiling in every position holds exactly five, so
#: a smaller cap would make the **first** contribution unplaceable: into
#: an empty portfolio the base is the contribution itself, the 20%
#: ceiling is R$ 200, and three slices leave R$ 400 with nowhere to go
#: for months.
#:
#: It rarely binds later. Once the portfolio is large enough for the
#: ceilings to have slack, `MAX_SHARE_PER_POSITION` caps the plan at
#: three meaningful slices anyway (40% + 40% + 20%).
MAX_POSITIONS = 5

#: Smallest amount worth sending anywhere. Below this the order is more
#: fee than investment, and the plan says so instead of emitting it.
MIN_TICKET = Decimal(100)

# -- what may be considered at all -----------------------------------

#: Least of the scoring formula a score must rest on to be a candidate.
#:
#: Half. Below that, what the number mostly reports is which pillars were
#: unavailable — see the module docstring.
MIN_COVERAGE = Decimal("0.50")

#: Width of a comparability band. Two candidates inside the same band are
#: treated as measuring the same thing; across bands, the better-covered
#: one wins regardless of score.
COVERAGE_TIER_WIDTH = Decimal("0.25")

#: Lowest score worth new money.
#:
#: The midpoint of the scale. A contribution is optional — there is
#: always the CDI — so an asset the calibrated thresholds place in the
#: bottom half is not bought merely for being the best of a bad universe.
MIN_SCORE = Decimal(50)

#: How far from its target a weight may sit before it is off-target.
#:
#: Two percentage points. Read by `targets.py`, and the reason it exists
#: is that a target is a number with more decimal places than a portfolio
#: can hold: without a band every asset is off-target forever, by
#: centavos, and the word stops meaning anything.
#:
#: Two rather than one because of what closing a gap costs. Correcting
#: 2 p.p. of a portfolio smaller than R$ 5.000 is an order below
#: `MIN_TICKET`, which the allocator already refuses to emit; above that
#: size it is inside the noise the next monthly contribution absorbs
#: anyway. Configurable like every other limit (rule 32).
REBALANCE_BAND = Decimal("0.02")


class Exclusion(str, Enum):
    """Why a candidate received nothing. Every skip carries one.

    Shared with `targets.py`, which reaches the same verdicts by testing
    merit instead of the final score — the vocabulary of "why did this
    asset get nothing" is one, even where the tests differ.
    """

    NOT_SCORABLE = "NOT_SCORABLE"
    NO_MERIT_SCORE = "NO_MERIT_SCORE"
    COVERAGE_BELOW_MINIMUM = "COVERAGE_BELOW_MINIMUM"
    SCORE_BELOW_MINIMUM = "SCORE_BELOW_MINIMUM"
    SECTOR_UNKNOWN = "SECTOR_UNKNOWN"
    ASSET_LIMIT_REACHED = "ASSET_LIMIT_REACHED"
    SECTOR_LIMIT_REACHED = "SECTOR_LIMIT_REACHED"
    BELOW_MINIMUM_TICKET = "BELOW_MINIMUM_TICKET"
    MAX_POSITIONS_REACHED = "MAX_POSITIONS_REACHED"
    CONTRIBUTION_EXHAUSTED = "CONTRIBUTION_EXHAUSTED"
    # Only the rebalancing plan reaches these two: they are verdicts
    # about a target, and the contribution plan does not consult one.
    WITHIN_BAND = "WITHIN_BAND"
    ABOVE_TARGET = "ABOVE_TARGET"


class Limit(str, Enum):
    """Which rule decided the size of an allocation.

    Shared with `rebalancing.py`, which adds one of its own: closing a
    gap stops at the target, a ceiling the contribution plan has no
    notion of.
    """

    TARGET_WEIGHT = "TARGET_WEIGHT"
    ASSET_WEIGHT = "ASSET_WEIGHT"
    SECTOR_WEIGHT = "SECTOR_WEIGHT"
    POSITION_SHARE = "POSITION_SHARE"
    CONTRIBUTION_REMAINING = "CONTRIBUTION_REMAINING"


@dataclass(frozen=True)
class AllocationPolicy:
    """The investor's limits, all of them adjustable (rule 32).

    Rule 32 is explicit that two conservative investors need not hold the
    same portfolio, so none of these is hard-coded into the algorithm.
    The defaults are one coherent conservative setting, not the only one.
    """

    max_asset_weight: Decimal = MAX_ASSET_WEIGHT
    max_sector_weight: Decimal = MAX_SECTOR_WEIGHT
    max_share_per_position: Decimal = MAX_SHARE_PER_POSITION
    max_positions: int = MAX_POSITIONS
    min_ticket: Decimal = MIN_TICKET
    min_coverage: Decimal = MIN_COVERAGE
    min_score: Decimal = MIN_SCORE
    coverage_tier_width: Decimal = COVERAGE_TIER_WIDTH
    rebalance_band: Decimal = REBALANCE_BAND
    #: Whether an asset with no sector recorded may be funded.
    #:
    #: `True` refuses it. A sector ceiling that cannot be evaluated is
    #: not a ceiling, and letting the asset through would mean the
    #: rule stops applying exactly where the data is thinnest — quietly
    #: rewarding whichever assets nobody filled the field in for. The
    #: fix is one field on the asset, so the refusal names it.
    require_sector: bool = True


DEFAULT_POLICY = AllocationPolicy()


@dataclass(frozen=True)
class Candidate:
    """One asset offered to the allocator, with what the portfolio holds.

    `held_amount` and the sector totals are cost basis in BRL, from the
    ledger. `score` is whatever `scoring.compose` produced — this module
    reads `final_score` and `coverage` and passes the pillars through
    untouched.
    """

    ticker: str
    asset_id: int
    name: str
    sector: str | None
    score: AssetScore
    held_amount: Decimal = ZERO


@dataclass(frozen=True)
class Allocation:
    """One line of the plan: an asset, an amount, and why that amount."""

    ticker: str
    asset_id: int
    name: str
    sector: str | None
    amount: Decimal
    rank: int
    final_score: Decimal
    coverage: Decimal
    coverage_tier: int
    #: What the concentration ceilings alone would have permitted, before
    #: the per-position share and the money actually left. Reported so
    #: "why only R$ 200?" is answerable from the line itself.
    headroom: Decimal
    limited_by: Limit
    weight_before: Decimal
    weight_after: Decimal
    score: AssetScore


@dataclass(frozen=True)
class Skipped:
    """One asset that received nothing, and the rule that stopped it."""

    ticker: str
    asset_id: int
    name: str
    reason: Exclusion
    detail: str
    final_score: Decimal | None
    coverage: Decimal


@dataclass(frozen=True)
class AllocationPlan:
    """The full answer, decomposable the way a score is.

    `allocated + unallocated == contribution` always. Money with nowhere
    to go under the limits is reported rather than forced somewhere, and
    `skipped` says what stopped each asset that could have taken it.
    """

    rules_version: str
    formula_version: str
    policy: AllocationPolicy
    contribution: Decimal
    allocated: Decimal
    unallocated: Decimal
    #: Portfolio value the weights are measured against: what is invested
    #: today plus the whole contribution, cash included.
    base_value: Decimal
    allocations: tuple[Allocation, ...]
    skipped: tuple[Skipped, ...]


def allocate_contribution(
    candidates: list[Candidate],
    invested: Decimal,
    sector_amounts: dict[str, Decimal],
    contribution: Decimal,
    policy: AllocationPolicy = DEFAULT_POLICY,
) -> AllocationPlan:
    """Split `contribution` across `candidates` under `policy`.

    `invested` is the portfolio's total cost basis and `sector_amounts`
    the part of it in each sector — both from the ledger, both excluding
    the contribution. They are passed in rather than derived from
    `candidates` because the portfolio can hold an asset the universe no
    longer offers, and its weight still counts against the ceilings.

    Candidates may arrive in any order; the result does not depend on it.
    Ranking is total — coverage tier, then score, then ticker — so two
    assets that tie on both numbers still resolve the same way every run
    (rule 113).
    """
    if contribution <= 0:
        raise ValueError("A contribution must be a positive amount.")

    contribution = floor_to_centavo(contribution)
    base = invested + contribution

    eligible: list[Candidate] = []
    skipped: list[Skipped] = []
    for candidate in candidates:
        reason = ineligibility(candidate, policy)
        if reason is None:
            eligible.append(candidate)
        else:
            skipped.append(_skip(candidate, *reason))

    eligible.sort(
        key=lambda item: (
            -_coverage_tier(item.score.coverage, policy),
            -(item.score.final_score or ZERO),
            item.ticker,
        )
    )

    # Sector room is consumed as the plan is built: two assets in the
    # same sector share one ceiling, and charging each of them the full
    # room would let the pair breach it together.
    sector_room = {
        sector: policy.max_sector_weight * base - amount
        for sector, amount in sector_amounts.items()
    }
    position_cap = floor_to_centavo(contribution * policy.max_share_per_position)

    allocations: list[Allocation] = []
    remaining = contribution

    for rank, candidate in enumerate(eligible, start=1):
        if len(allocations) >= policy.max_positions:
            skipped.append(
                _skip(
                    candidate,
                    Exclusion.MAX_POSITIONS_REACHED,
                    f"The plan already funds {policy.max_positions} positions.",
                )
            )
            continue
        if remaining < policy.min_ticket:
            skipped.append(
                _skip(
                    candidate,
                    Exclusion.CONTRIBUTION_EXHAUSTED,
                    f"Only R$ {remaining} of the contribution was left, below "
                    f"the R$ {policy.min_ticket} minimum ticket.",
                )
            )
            continue

        asset_room = policy.max_asset_weight * base - candidate.held_amount
        if asset_room <= 0:
            skipped.append(
                _skip(
                    candidate,
                    Exclusion.ASSET_LIMIT_REACHED,
                    f"Already at {percent(candidate.held_amount / base)} of the "
                    f"portfolio, at or above the "
                    f"{percent(policy.max_asset_weight)} ceiling.",
                )
            )
            continue

        sector = candidate.sector
        room_in_sector = (
            sector_room.get(sector, policy.max_sector_weight * base)
            if sector is not None
            else None
        )
        if room_in_sector is not None and room_in_sector <= 0:
            skipped.append(
                _skip(
                    candidate,
                    Exclusion.SECTOR_LIMIT_REACHED,
                    f"Sector {sector} is at or above the "
                    f"{percent(policy.max_sector_weight)} ceiling.",
                )
            )
            continue

        headroom = (
            asset_room if room_in_sector is None else min(asset_room, room_in_sector)
        )
        allowance = min(headroom, position_cap, remaining)
        amount = floor_to_centavo(allowance)

        if amount < policy.min_ticket:
            skipped.append(
                _skip(
                    candidate,
                    Exclusion.BELOW_MINIMUM_TICKET,
                    f"Only R$ {amount} could be placed here, below the "
                    f"R$ {policy.min_ticket} minimum ticket.",
                )
            )
            continue

        allocations.append(
            Allocation(
                ticker=candidate.ticker,
                asset_id=candidate.asset_id,
                name=candidate.name,
                sector=sector,
                amount=amount,
                rank=rank,
                # `_ineligibility` rejected a None score already, so
                # `final_score` is set here; the fallback keeps the
                # type checker honest.
                final_score=candidate.score.final_score or ZERO,
                coverage=candidate.score.coverage,
                coverage_tier=_coverage_tier(candidate.score.coverage, policy),
                headroom=floor_to_centavo(headroom),
                limited_by=_binding_limit(
                    allowance, asset_room, room_in_sector, position_cap
                ),
                weight_before=candidate.held_amount / base,
                weight_after=(candidate.held_amount + amount) / base,
                score=candidate.score,
            )
        )
        remaining -= amount
        if sector is not None:
            sector_room[sector] = (
                sector_room.get(sector, policy.max_sector_weight * base) - amount
            )

    allocated = sum((item.amount for item in allocations), ZERO)
    return AllocationPlan(
        rules_version=ALLOCATION_RULES_VERSION,
        formula_version=SCORING_FORMULA_VERSION,
        policy=policy,
        contribution=contribution,
        allocated=allocated,
        unallocated=contribution - allocated,
        base_value=base,
        allocations=tuple(allocations),
        skipped=tuple(skipped),
    )


# -- helpers ---------------------------------------------------------


def ineligibility(
    candidate: Candidate, policy: AllocationPolicy
) -> tuple[Exclusion, str] | None:
    """Why this candidate cannot be funded, before any money is counted.

    Only the tests that depend on the score and the asset itself. What
    depends on how much room is left runs inside the ranked loop, so its
    reason reflects the state of the plan at the moment it applied.
    """
    score = candidate.score
    if score.final_score is None:
        missing = ", ".join(
            sub.name for sub in score.sub_scores if not sub.is_available
        )
        return (
            Exclusion.NOT_SCORABLE,
            f"No final score: too few pillars available ({missing} missing).",
        )
    if score.coverage < policy.min_coverage:
        return (
            Exclusion.COVERAGE_BELOW_MINIMUM,
            (
                f"The score rests on {percent(score.coverage)} of the "
                f"formula, below the {percent(policy.min_coverage)} minimum."
            ),
        )
    if score.final_score < policy.min_score:
        return (
            Exclusion.SCORE_BELOW_MINIMUM,
            (
                f"Scored {round_score(score.final_score)}, below the "
                f"{round_score(policy.min_score)} minimum."
            ),
        )
    if policy.require_sector and candidate.sector is None:
        return (
            Exclusion.SECTOR_UNKNOWN,
            "No sector recorded, so the sector ceiling cannot be applied.",
        )
    return None


def _coverage_tier(coverage: Decimal, policy: AllocationPolicy) -> int:
    """Which comparability band a coverage falls in.

    Bands rather than the raw number so that 0.80 and 0.85 — the same
    score missing slightly different pillars — are not put in a strict
    order they cannot support.
    """
    if policy.coverage_tier_width <= 0:  # pragma: no cover - a bad policy
        raise ValueError("coverage_tier_width must be positive.")
    return int(coverage / policy.coverage_tier_width)


def _binding_limit(
    allowance: Decimal,
    asset_room: Decimal,
    sector_room: Decimal | None,
    position_cap: Decimal,
) -> Limit:
    """Which of the four ceilings actually decided the amount.

    Checked in a fixed order so a tie always reports the same rule; the
    concentration ceilings come first because they are the ones the
    investor set.
    """
    if allowance == asset_room:
        return Limit.ASSET_WEIGHT
    if sector_room is not None and allowance == sector_room:
        return Limit.SECTOR_WEIGHT
    if allowance == position_cap:
        return Limit.POSITION_SHARE
    return Limit.CONTRIBUTION_REMAINING


def _skip(candidate: Candidate, reason: Exclusion, detail: str) -> Skipped:
    return Skipped(
        ticker=candidate.ticker,
        asset_id=candidate.asset_id,
        name=candidate.name,
        reason=reason,
        detail=detail,
        final_score=candidate.score.final_score,
        coverage=candidate.score.coverage,
    )


def floor_to_centavo(value: Decimal) -> Decimal:
    """Money, rounded **down** to the centavo.

    Public because `rebalancing.py` sizes orders in the same currency
    under the same rule, and a second copy of a rounding decision is a
    second chance to round the other way.

    Down, never nearest: rounding up could push an allocation past a
    ceiling by a centavo, and a plan that violates its own limits in the
    last decimal is still a plan that violates them. The residue lands in
    `unallocated`, where it is visible.
    """
    return value.quantize(CENTAVO, rounding=ROUND_DOWN)


def percent(fraction: Decimal) -> str:
    return f"{(fraction * 100).quantize(Decimal('0.1'))}%"


def round_score(score: Decimal) -> Decimal:
    return score.quantize(Decimal("0.1"))
