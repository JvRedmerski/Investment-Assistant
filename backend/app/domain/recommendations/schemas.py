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
