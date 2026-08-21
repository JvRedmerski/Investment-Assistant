"""The contribution that closes the gaps (roadmap §22, AGENTS.md rule 34).

Pure, deterministic and I/O-free, like `targets.py` and `allocation.py`.
Loading lives in `service.py`.

`targets.py` says how far the portfolio is from where it should be. This
says what to do about it with the money actually arriving this month.

## Rebalancing here means steering new money, never selling

Rule 34 lists what the recommendation must prioritise and every item is
buy-side: *"ativos que estejam abaixo do peso-alvo"*. This module holds
to that literally — it never emits a sale, and an overweight position is
closed by dilution over subsequent contributions rather than by trimming.

That is not squeamishness, it is the arithmetic of the investor this
project is for. A sale realises capital gains tax on a portfolio whose
whole thesis is compounding, and it pays brokerage on both legs to move
money the monthly contribution would have moved for free. With ~R$ 1.000
arriving every month against a portfolio of a few tens of thousands, cash
flow is a large enough lever to correct drift on its own.

The consequence is stated rather than hidden: a portfolio far above
target in one name **stays** far above it for a while, and the drift
table keeps saying so.

## Every gap is measured against the portfolio *after* the money lands

The drift table measures weights against what is invested today, because
that is what the investor holds. A plan cannot use that number to decide
anything, and the reason showed up against the real database rather than
in a unit test.

A portfolio of R$ 1.200 — R$ 300 in a rated name against a 20% target,
R$ 900 in one nothing can rate — reads as 25% and therefore *above*
target. Refuse to fund it on that reading and R$ 1.000 of contribution
sits in cash, the base becomes R$ 2.200, and the same position is now
13.6%: **further** below its target than before the money arrived, having
been refused for being above it.

So the eligibility gate, the band and the ranking all run on
`held / (invested + contribution)`. Every other quantity here — `needed`,
the sector room, the per-asset room — was already on that base; using the
pre-contribution weight for the gate alone was the inconsistency.

Both readings reach the investor. Each line carries `weight_gap` as the
drift table reported it and `needed` as the money the plan acted on, and
the two answer different questions.

## Ranking is by gap, and that is not the allocator's ranking

`allocation.py` ranks by coverage tier and then by score, and needs the
tiers because it is comparing scores that rest on different amounts of
evidence. Here the ranking is the gap — how far below its destination
each asset sits — and the tiers are already spent: a target only exists
for an asset whose **merit** cleared the coverage floor, so everything
that reaches this ranking has passed the same test.

Two plans, two orders, one policy. The contribution plan answers "where
does new money do the most good"; this one answers "what is furthest
from where it should be".

## The target is the binding ceiling, and it subsumes the per-asset one

An allocation stops at `target * base - held`: the money that takes the
asset exactly to its target weight, measured against the portfolio *after*
the contribution. Since no target can exceed `max_asset_weight`, that
amount is never more than the per-asset ceiling would have allowed — the
per-asset ceiling is still evaluated, and cannot bind.

The **sector** ceiling can still bind, and the case is real rather than
theoretical: a sector held heavily in an asset the model cannot rate has
no target of its own to stop it, and funding a rated name inside it would
push the sector past its limit anyway.

## `max_share_per_position` deliberately does not apply

The contribution plan caps any one asset at 40% of a contribution because
it ranks by score, a noisy estimate, and a month's money landing
undiluted on one noisy ranking is a risk worth hedging.

This plan makes no fresh judgement about which asset is best. It closes a
**measured** distance to a destination that the concentration ceilings
already capped, and overshoot is structurally impossible because the
target binds first. The hedge would have nothing to protect against, and
would instead leave money idle in the one case the investor most wants it
spent: a single large gap and everything else on target.

## Nothing is stored

A plan is derived, never persisted (rule 16, ADR-002).
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.recommendations.allocation import (
    DEFAULT_POLICY,
    AllocationPolicy,
    Exclusion,
    Limit,
    floor_to_centavo,
    percent,
)
from app.domain.recommendations.targets import AssetTarget, PortfolioTargets

ZERO = Decimal(0)

#: Version of the rebalancing rules: the ranking and the sizing.
#:
#: A fourth version alongside the scoring formula, the allocation rules
#: and the target model, for the same reason those are three and not one
#: — they change independently, and a plan records all of them (rule 30).
REBALANCE_RULES_VERSION = "1.0.0"


@dataclass(frozen=True)
class RebalanceAllocation:
    """One line of the plan: an asset, an amount, and the gap it closes.

    `weight_gap` and `current_weight` are as the drift table reported
    them, measured against the portfolio **before** the contribution.
    `weight_after` and `gap_after` are measured against it after, which
    is why they do not simply differ by `amount / base`: putting money in
    also grows the denominator.
    """

    ticker: str
    asset_id: int
    name: str
    sector: str | None
    amount: Decimal
    rank: int
    merit_score: Decimal | None
    current_weight: Decimal
    target_weight: Decimal
    weight_gap: Decimal
    #: What it would take to reach the target outright, on the
    #: post-contribution base. Reported so "why only R$ 200?" is
    #: answerable from the line itself.
    needed: Decimal
    limited_by: Limit
    weight_after: Decimal
    gap_after: Decimal
    detail: str


@dataclass(frozen=True)
class RebalanceSkipped:
    """One asset that received nothing, and the rule that stopped it."""

    ticker: str
    asset_id: int
    name: str
    reason: Exclusion
    detail: str
    current_weight: Decimal
    target_weight: Decimal
    weight_gap: Decimal


@dataclass(frozen=True)
class RebalancePlan:
    """The full answer, decomposable the way the drift table is.

    `allocated + unallocated == contribution` always. `underweight_after`
    is the distance still left once the plan is executed, and it is not
    guaranteed to be smaller than `underweight_before`: money the limits
    leave unplaced sits as cash inside the base and dilutes every weight,
    including the ones that were already on target. Reporting both is the
    only way that shows.
    """

    rules_version: str
    model_version: str
    formula_version: str
    policy: AllocationPolicy
    contribution: Decimal
    allocated: Decimal
    unallocated: Decimal
    #: Portfolio value the after-weights are measured against: what is
    #: invested today plus the whole contribution, cash included.
    base_value: Decimal
    underweight_before: Decimal
    underweight_after: Decimal
    allocations: tuple[RebalanceAllocation, ...]
    skipped: tuple[RebalanceSkipped, ...]


def rebalance_contribution(
    targets: PortfolioTargets,
    sector_amounts: dict[str, Decimal],
    contribution: Decimal,
    policy: AllocationPolicy = DEFAULT_POLICY,
) -> RebalancePlan:
    """Spend `contribution` closing the gaps in `targets`, largest first.

    `sector_amounts` is the cost basis held in each sector, excluding the
    contribution. It is passed in rather than summed from the rows for
    the same reason the allocator takes it: the portfolio can hold an
    asset the universe no longer offers, and that money still counts
    against the sector ceiling.

    The rows arrive ordered by the drift table's gaps, and are ordered
    again here on the post-contribution basis — the two orders are not
    the same, because dilution does not move every weight by the same
    amount. The ticker breaks ties, so this one is total too (rule 113).
    """
    if contribution <= 0:
        raise ValueError("A contribution must be a positive amount.")

    contribution = floor_to_centavo(contribution)
    base = targets.invested + contribution

    sector_room = {
        sector: policy.max_sector_weight * base - amount
        for sector, amount in sector_amounts.items()
    }

    # What each weight becomes if this plan adds nothing to it. Every
    # decision below is taken against this, never against the weight the
    # drift table reported — see the module docstring.
    diluted = {
        row.ticker: row.held_amount / base if base > 0 else ZERO
        for row in targets.targets
    }
    ordered = sorted(
        targets.targets,
        key=lambda row: (-(row.target_weight - diluted[row.ticker]), row.ticker),
    )

    allocations: list[RebalanceAllocation] = []
    skipped: list[RebalanceSkipped] = []
    remaining = contribution
    rank = 0

    for row in ordered:
        reason = _not_a_candidate(row, diluted[row.ticker], policy)
        if reason is not None:
            skipped.append(_skip(row, *reason))
            continue

        rank += 1
        if len(allocations) >= policy.max_positions:
            skipped.append(
                _skip(
                    row,
                    Exclusion.MAX_POSITIONS_REACHED,
                    f"The plan already funds {policy.max_positions} positions.",
                )
            )
            continue
        if remaining < policy.min_ticket:
            skipped.append(
                _skip(
                    row,
                    Exclusion.CONTRIBUTION_EXHAUSTED,
                    f"Only R$ {remaining} of the contribution was left, below "
                    f"the R$ {policy.min_ticket} minimum ticket.",
                )
            )
            continue

        # Strictly positive: `_not_a_candidate` already established
        # that the target is more than a band above the diluted weight,
        # and this is that difference expressed in money.
        needed = row.target_weight * base - row.held_amount
        asset_room = policy.max_asset_weight * base - row.held_amount

        room_in_sector = (
            sector_room.get(row.sector, policy.max_sector_weight * base)
            if row.sector is not None
            else None
        )
        if room_in_sector is not None and room_in_sector <= 0:
            skipped.append(
                _skip(
                    row,
                    Exclusion.SECTOR_LIMIT_REACHED,
                    f"Sector {row.sector} is at or above the "
                    f"{percent(policy.max_sector_weight)} ceiling, so there "
                    f"is no room to close this gap from here.",
                )
            )
            continue

        allowance = min(
            needed,
            asset_room,
            remaining,
            *([room_in_sector] if room_in_sector is not None else []),
        )
        amount = floor_to_centavo(allowance)

        if amount < policy.min_ticket:
            skipped.append(
                _skip(
                    row,
                    Exclusion.BELOW_MINIMUM_TICKET,
                    f"Only R$ {amount} could be placed here, below the "
                    f"R$ {policy.min_ticket} minimum ticket.",
                )
            )
            continue

        after = (row.held_amount + amount) / base
        allocations.append(
            RebalanceAllocation(
                ticker=row.ticker,
                asset_id=row.asset_id,
                name=row.name,
                sector=row.sector,
                amount=amount,
                rank=rank,
                merit_score=row.merit_score,
                current_weight=row.current_weight,
                target_weight=row.target_weight,
                weight_gap=row.weight_gap,
                needed=floor_to_centavo(needed),
                limited_by=_binding_limit(
                    allowance, needed, room_in_sector, asset_room
                ),
                weight_after=after,
                gap_after=row.target_weight - after,
                detail=_why(allowance, needed, room_in_sector, asset_room, policy),
            )
        )
        remaining -= amount
        if row.sector is not None:
            sector_room[row.sector] = (
                sector_room.get(row.sector, policy.max_sector_weight * base) - amount
            )

    allocated = sum((item.amount for item in allocations), ZERO)
    return RebalancePlan(
        rules_version=REBALANCE_RULES_VERSION,
        model_version=targets.model_version,
        formula_version=targets.formula_version,
        policy=policy,
        contribution=contribution,
        allocated=allocated,
        unallocated=contribution - allocated,
        base_value=base,
        underweight_before=targets.underweight_gap,
        underweight_after=_underweight_after(targets, allocations, base),
        allocations=tuple(allocations),
        skipped=tuple(skipped),
    )


# -- helpers ---------------------------------------------------------


def _not_a_candidate(
    row: AssetTarget, diluted: Decimal, policy: AllocationPolicy
) -> tuple[Exclusion, str] | None:
    """Why this row cannot be funded, before any money is counted.

    `diluted` is the weight this asset falls to if the plan adds nothing
    — the basis every decision here is taken on, and not the weight the
    drift table reported. `DriftStatus` is deliberately not consulted:
    it is the verdict on the portfolio as it stands, and this is a
    verdict on the portfolio the contribution creates.

    An asset with no target does carry the table's own verdict forward,
    because that one does not depend on the basis: there is a single
    reason it has no destination, and restating it in different words
    would let the two drift apart.
    """
    if row.excluded is not None:
        return (row.excluded, row.detail)

    gap = row.target_weight - diluted
    if gap < -policy.rebalance_band:
        return (
            Exclusion.ABOVE_TARGET,
            (
                f"Still at {percent(diluted)} once this contribution is in, "
                f"against a target of {percent(row.target_weight)}. Nothing "
                f"here sells; later contributions close this by dilution."
            ),
        )
    if gap <= policy.rebalance_band:
        return (
            Exclusion.WITHIN_BAND,
            (
                f"Within {percent(policy.rebalance_band)} of its target once "
                f"this contribution is in, so buying here is churn rather "
                f"than correction."
            ),
        )
    return None


def _binding_limit(
    allowance: Decimal,
    needed: Decimal,
    sector_room: Decimal | None,
    asset_room: Decimal,
) -> Limit:
    """Which ceiling actually decided the amount.

    The target is checked first, so a tie reports it. That is the right
    tie to break this way: `asset_room` can only equal `needed` when the
    target *is* the per-asset ceiling, and the target is the rule that
    defines this plan.
    """
    if allowance == needed:
        return Limit.TARGET_WEIGHT
    if sector_room is not None and allowance == sector_room:
        return Limit.SECTOR_WEIGHT
    if allowance == asset_room:  # pragma: no cover - cannot bind first
        return Limit.ASSET_WEIGHT
    return Limit.CONTRIBUTION_REMAINING


def _why(
    allowance: Decimal,
    needed: Decimal,
    sector_room: Decimal | None,
    asset_room: Decimal,
    policy: AllocationPolicy,
) -> str:
    limit = _binding_limit(allowance, needed, sector_room, asset_room)
    if limit is Limit.TARGET_WEIGHT:
        return "Enough to reach the target; more would overshoot it."
    if limit is Limit.SECTOR_WEIGHT:
        return (
            f"Cut short by the {percent(policy.max_sector_weight)} sector "
            f"ceiling, which this gap cannot be closed through."
        )
    if limit is Limit.ASSET_WEIGHT:  # pragma: no cover - cannot bind first
        return f"Cut short by the {percent(policy.max_asset_weight)} ceiling."
    return "All that was left of the contribution."


def _underweight_after(
    targets: PortfolioTargets,
    allocations: list[RebalanceAllocation],
    base: Decimal,
) -> Decimal:
    """Distance still to go once the plan is executed.

    Measured over **every** row, not just the funded ones, and against
    the post-contribution base. A row nobody funded is further from its
    target afterwards than before, because the money that went elsewhere
    — or stayed as cash — grew the denominator underneath it. Netting
    that out would flatter the plan.
    """
    placed = {item.ticker: item.amount for item in allocations}
    total = ZERO
    for row in targets.targets:
        after = (row.held_amount + placed.get(row.ticker, ZERO)) / base
        total += max(row.target_weight - after, ZERO)
    return total


def _skip(row: AssetTarget, reason: Exclusion, detail: str) -> RebalanceSkipped:
    return RebalanceSkipped(
        ticker=row.ticker,
        asset_id=row.asset_id,
        name=row.name,
        reason=reason,
        detail=detail,
        current_weight=row.current_weight,
        target_weight=row.target_weight,
        weight_gap=row.weight_gap,
    )
