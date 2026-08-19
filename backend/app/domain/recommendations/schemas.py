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
