from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SubScoreResponse(BaseModel):
    """One pillar of an asset's score.

    `value` is 0-100 where 100 is best for the investor, or `null` when
    the pillar could not be computed — never a stand-in zero (ADR-014).

    `components` shows each contributing metric already on the 0-100
    scale, and `missing` names the inputs that were absent. Together they
    make the pillar explainable without re-running anything, which is
    what rule 30 means by decomposable.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    value: Decimal | None
    weight: Decimal
    components: dict[str, Decimal]
    missing: tuple[str, ...]


class AssetScoreResponse(BaseModel):
    """An asset scored against one portfolio.

    ⚠️ **`coverage` is required reading, not a diagnostic.** It is the
    fraction of the intended formula the score actually rests on, and two
    scores with different coverage are **not comparable** even though
    both are numbers between 0 and 100. An asset scored on Risk alone is
    not being measured on the same thing as one scored on all five
    pillars.

    `final_score` is `null` when fewer than two pillars were available: a
    composite of one is that one under another name.

    `formula_version` identifies the weights and thresholds that produced
    these numbers (rule 30 — the formula is versioned).
    """

    ticker: str
    asset_id: int
    name: str
    sector: str | None
    formula_version: str
    final_score: Decimal | None
    coverage: Decimal
    sub_scores: list[SubScoreResponse]


class PortfolioScoresResponse(BaseModel):
    """Every tracked asset, scored against one portfolio.

    Ordered best first, with unscorable assets last rather than dropped —
    "this cannot be scored, and here is what is missing" is an answer the
    investor needs, and hiding those rows would make the gap invisible.

    Scores are **relative to this portfolio**: the Diversification pillar
    reads the portfolio's current concentration, so the same asset scores
    differently for someone who already holds 15% of it (rule 31).
    """

    portfolio_id: int
    formula_version: str
    scores: list[AssetScoreResponse]


class AllocationPolicyResponse(BaseModel):
    """The limits the plan was computed under (AGENTS.md rule 32).

    Echoed back with every plan, because "conservative" is a set of
    numbers rather than a label, and two investors are not required to
    use the same ones. A plan is only interpretable next to the policy
    that produced it.
    """

    max_asset_weight: Decimal
    max_sector_weight: Decimal
    max_share_per_position: Decimal
    max_positions: int
    min_ticket: Decimal
    min_coverage: Decimal
    min_score: Decimal
    coverage_tier_width: Decimal
    #: Read by the drift table, not by the contribution plan: how far
    #: from its target a weight may sit before it counts as off-target.
    rebalance_band: Decimal
    require_sector: bool


class AllocationResponse(BaseModel):
    """One line of the plan: an asset, an amount, and the reason for it.

    `limited_by` names the rule that decided the size — a concentration
    ceiling, the per-position share, or simply the money left. Together
    with `headroom` it answers "why only this much?" without re-running
    anything, which is the same standard `SubScoreResponse` holds the
    score to.

    `coverage_tier` is the comparability band: scores are ranked against
    each other **inside** a band and never across, so a lower tier is
    funded only with what the tier above could not absorb.
    """

    ticker: str
    asset_id: int
    name: str
    sector: str | None
    amount: Decimal
    rank: int
    final_score: Decimal
    coverage: Decimal
    coverage_tier: int
    headroom: Decimal
    limited_by: str
    weight_before: Decimal
    weight_after: Decimal
    sub_scores: list[SubScoreResponse]


class SkippedCandidateResponse(BaseModel):
    """One asset that received nothing, and the rule that stopped it.

    Reported rather than dropped, for the reason the scores are: "this
    got nothing, and here is why" is an answer the investor needs, and
    an empty list of allocations with no explanation is not one.
    """

    ticker: str
    asset_id: int
    name: str
    reason: str
    detail: str
    final_score: Decimal | None
    coverage: Decimal


class ContributionPlanResponse(BaseModel):
    """Where the next contribution goes (AGENTS.md rules 31/32/33).

    `allocated + unallocated == contribution` always. Money the limits
    leave unplaceable is reported as `unallocated` instead of being
    forced somewhere, and `skipped` says what stopped each asset that
    could otherwise have taken it.

    `base_value` is what the weights are measured against: the portfolio
    once this contribution is in, cash included.

    Both versions are recorded — `formula_version` for the scores this
    consumed and `rules_version` for the allocation rules applied — so a
    plan can always be traced back to what produced it (rule 30).
    """

    portfolio_id: int
    rules_version: str
    formula_version: str
    policy: AllocationPolicyResponse
    contribution: Decimal
    allocated: Decimal
    unallocated: Decimal
    base_value: Decimal
    allocations: list[AllocationResponse]
    skipped: list[SkippedCandidateResponse]


class AssetTargetResponse(BaseModel):
    """One row of the drift table (AGENTS.md rule 34).

    `weight_gap` is `target_weight - current_weight` as a fraction, so
    0.04 is the +4 p.p. of the rule's own example. Positive means the
    portfolio is **under** its target and a contribution here closes the
    gap.

    ⚠️ **`merit_score` is not `final_score`, and the difference is the
    point.** Merit is Quality, Valuation, Growth and Risk recomposed
    without the Diversification pillar, because that pillar reads the
    portfolio being targeted: a target proportional to `final_score`
    recedes as the portfolio approaches it (ADR-027). `final_score` is
    still reported, because it is what the contribution plan ranks by.

    `excluded` is set when the asset has no target at all, and `detail`
    says why in words. A target of 0 on a position the investor holds is
    **not** an instruction to sell — nothing in this project sells; it is
    a gap that monthly contributions close by dilution.
    """

    ticker: str
    asset_id: int
    name: str
    sector: str | None
    merit_score: Decimal | None
    merit_coverage: Decimal
    current_weight: Decimal
    target_weight: Decimal
    weight_gap: Decimal
    status: str
    limited_by: str | None
    excluded: str | None
    detail: str
    final_score: Decimal | None
    coverage: Decimal
    sub_scores: list[SubScoreResponse]


class PortfolioTargetsResponse(BaseModel):
    """Where the portfolio is against where it should be (rule 34).

    `assigned + unassigned == 1` always. `unassigned` is the share of the
    portfolio the ceilings could not hand to anybody — with few rateable
    assets it is most of it, and it is reported rather than spread over
    whoever happened to be rateable.

    `underweight_gap` and `overweight_gap` are the two directions summed
    separately, never netted: one is closed by contributing and the other
    only by selling or by dilution, and a single figure would hide which.

    `untracked_weight` is the share held in assets that were not offered
    as candidates — a deactivated holding still counts in `invested`, and
    without this the rows would not add up to the portfolio.

    Three versions are recorded (rule 30): `formula_version` for the
    scores consumed, `model_version` for the target model, and the policy
    echoed in full.
    """

    portfolio_id: int
    model_version: str
    formula_version: str
    policy: AllocationPolicyResponse
    invested: Decimal
    assigned: Decimal
    unassigned: Decimal
    underweight_gap: Decimal
    overweight_gap: Decimal
    untracked_weight: Decimal
    targets: list[AssetTargetResponse]


class RebalanceAllocationResponse(BaseModel):
    """One line of the rebalancing plan (AGENTS.md rule 34).

    `current_weight` and `weight_gap` are as the drift table reported
    them, against the portfolio **before** the contribution.
    `weight_after` and `gap_after` are against it after — they do not
    simply differ by `amount / base_value`, because putting money in also
    grows the denominator.

    `needed` is what closing the gap outright would take, so "why only
    R$ 200?" is answerable from the line itself, and `limited_by` names
    the rule that decided the amount.
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
    needed: Decimal
    limited_by: str
    weight_after: Decimal
    gap_after: Decimal
    detail: str


class RebalanceSkippedResponse(BaseModel):
    """One asset the plan did not fund, and the rule that stopped it."""

    ticker: str
    asset_id: int
    name: str
    reason: str
    detail: str
    current_weight: Decimal
    target_weight: Decimal
    weight_gap: Decimal


class RebalancePlanResponse(BaseModel):
    """How this contribution closes the gaps (rule 34).

    ⚠️ **Nothing here sells.** Every item rule 34 asks the recommendation
    to prioritise is buy-side, and an overweight position is closed by
    dilution over later contributions rather than by trimming — a sale
    realises tax on a portfolio whose thesis is compounding, and pays
    brokerage on both legs to move money the next contribution moves for
    free. An asset above its target therefore appears in `skipped` with
    `ABOVE_TARGET`, and it will keep appearing there for a while.

    `allocated + unallocated == contribution` always.

    `underweight_after` is **not** guaranteed to be below
    `underweight_before`: money the limits leave unplaced stays as cash
    inside `base_value` and dilutes every weight, including those already
    on target. Both are reported because that is the only way it shows.

    Four versions are recorded (rule 30): the scores consumed, the target
    model, these rules, and the policy echoed in full.
    """

    portfolio_id: int
    rules_version: str
    model_version: str
    formula_version: str
    policy: AllocationPolicyResponse
    contribution: Decimal
    allocated: Decimal
    unallocated: Decimal
    base_value: Decimal
    underweight_before: Decimal
    underweight_after: Decimal
    allocations: list[RebalanceAllocationResponse]
    skipped: list[RebalanceSkippedResponse]
