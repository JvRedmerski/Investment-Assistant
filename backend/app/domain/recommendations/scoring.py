"""Asset sub-scores (AGENTS.md rules 30 and 113, roadmap §21).

Pure, deterministic and I/O-free. Every number here is either read from
an argument or derived from `app.quant` — nothing is fetched, nothing is
timed, nothing is random. Same input, same score, forever (rule 113).

## Decomposable, and the formula is the code

Rule 30 requires the score to be decomposable, the formula explicit and
versioned, and the weights never hidden inside an AI prompt. So:

- Each pillar returns a `SubScore` carrying **its own components** and
  the names of the inputs it could not get. A caller can always answer
  "why is this 62?" without re-running anything.
- Every threshold lives in a named constant below, next to the reason it
  has that value. There is no tuning parameter that is not visible here.
- `SCORING_FORMULA_VERSION` changes whenever a weight or a threshold
  changes, so a stored score can always be traced to the formula that
  produced it.

The AI layer (Wave 12) will be allowed to *explain* these numbers and
never to produce them (rule 3, ADR-009).

## Missing data is a first-class answer, not a zero

A pillar with no inputs returns `value=None`, never `0` and never a
"neutral" 50. ADR-014 already settled that for indicators, and the reason
is sharper here: a fabricated Quality Score does not look wrong, it looks
like a bad company. It would then be averaged into the final score and
become invisible.

That is not hypothetical, and it has now been demonstrated twice. When
this module was written the three fundamentals pillars — Quality,
Valuation, Growth — had **no data at all**, because the vendor's
statement modules had left its free plan. Ingesting the CVM filings
(W09-002) lit up Quality and Growth, and the per-period share count
(W09-003) lit up Valuation, both **with no change to this module**. The
absence was visible, and it closed by itself when the data arrived.

Absence is also permanent for whole asset classes, not a temporary state
of the project: an FII or an ETF has no income statement to score for
Quality, and never will.

## The final score, and why `coverage` is not decoration

`compose` averages the available pillars, renormalising their weights
over what was actually available. That is the only sensible arithmetic,
and it hides a trap: an asset scored on Risk alone and an asset scored on
all five are **not comparable**, even though both come back as a number
between 0 and 100.

So `AssetScore.coverage` reports the fraction of the intended formula the
score actually rests on, and it is a required part of the result rather
than a diagnostic. A consumer ranking assets must either compare only
equal coverage or demand a minimum — see the allocation step.

A final score also needs at least `MIN_SUB_SCORES` pillars. A composite
built from one component is that component wearing a different name, and
naming it "Final Score" invites exactly the comparison above.

## Units

Sub-scores are **0 to 100**, where 100 is best for the investor. Note
that this inverts for several inputs: lower volatility, lower P/E and a
shallower drawdown all score *higher*. The direction is stated on every
scale.

Indicator inputs are fractions, as `app.domain.fundamentals.indicators`
produces them (`0.15` is 15%), except `pe`, `pb` and `debt_ebitda`, which
are dimensionless multiples.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.quant.returns import Periodicity, PricePoint
from app.quant.risk import beta, max_drawdown, sharpe, volatility

#: Version of the formula below: weights, thresholds and composition.
#:
#: Bump it whenever any constant in this module changes, so a score
#: stored under an older version is never silently compared with a newer
#: one (rule 30 — the formula must be versioned).
SCORING_FORMULA_VERSION = "1.0.0"

#: Fewest pillars a final score may be composed from.
#:
#: Two, because a "composite" of one is that one wearing a different
#: name. See the module docstring.
MIN_SUB_SCORES = 2

BEST = Decimal(100)
WORST = Decimal(0)


@dataclass(frozen=True)
class Scale:
    """A linear map from a raw metric onto 0-100, clamped at both ends.

    `at_zero` is the raw value that scores 0 and `at_hundred` the one
    that scores 100. Putting them in that order — rather than as
    min/max plus a direction flag — means an inverted metric is written
    the way it reads: volatility scores 100 at 0.15 and 0 at 0.60, so
    `Scale(Decimal("0.60"), Decimal("0.15"))`.

    Clamping is deliberate: a company with 80% ROE does not deserve a
    score of 400, and extrapolating past the calibrated range would let
    one extreme input dominate a pillar.
    """

    at_zero: Decimal
    at_hundred: Decimal

    def __call__(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        span = self.at_hundred - self.at_zero
        if span == 0:  # pragma: no cover - a degenerate scale is a bug
            raise ValueError("Scale needs two distinct calibration points.")
        ratio = (value - self.at_zero) / span
        return min(max(ratio, Decimal(0)), Decimal(1)) * BEST


# -- Quality: is this a good business? -------------------------------
#
# Calibrated for the Brazilian market, where the risk-free rate itself
# runs into double digits: a 10% ROE is not "fine" here the way it might
# be elsewhere, because the investor can get more than that from the CDI
# with no equity risk at all. Hence 20% for full marks.

ROE_SCALE = Scale(Decimal(0), Decimal("0.20"))
ROIC_SCALE = Scale(Decimal(0), Decimal("0.15"))
NET_MARGIN_SCALE = Scale(Decimal(0), Decimal("0.20"))

# -- Valuation: is it cheap? -----------------------------------------
#
# Inverted scales: a lower multiple scores higher.
#
# ⚠️ The inversion has a trap, and clamping does NOT save you from it. A
# negative P/E is *lower* than 5, so it lands past the hundred end and
# would clamp to a perfect 100 — scoring a company that lost money as the
# cheapest thing on the exchange. Same for a negative P/B, which means
# negative book equity.
#
# A non-positive multiple is not a cheap one; it is a ratio that has
# stopped being a valuation measure at all. `score_valuation` therefore
# floors it explicitly rather than relying on the scale, and the tests
# pin both directions.

PE_SCALE = Scale(Decimal(25), Decimal(5))
PB_SCALE = Scale(Decimal(4), Decimal("0.5"))

# -- Growth ----------------------------------------------------------
#
# Symmetric around zero, so flat growth scores 50 rather than 0. A
# company that is not growing is not thereby failing, and a floor at 0%
# would score stagnation and collapse identically.

REVENUE_GROWTH_SCALE = Scale(Decimal("-0.20"), Decimal("0.20"))
PROFIT_GROWTH_SCALE = Scale(Decimal("-0.20"), Decimal("0.20"))

# -- Risk: calibrated for a conservative profile (rule 32) ------------
#
# Rule 32 says "conservative" must be a quantitative restriction rather
# than an adjective, and these are it. They deliberately punish
# volatility harder than a growth-oriented calibration would.

VOLATILITY_SCALE = Scale(Decimal("0.60"), Decimal("0.15"))
DRAWDOWN_SCALE = Scale(Decimal("-0.50"), Decimal(0))
#: Beta at or below 0.5 scores full marks, at or above 1.5 scores zero.
#: A negative beta lands past the top end and scores 100 — correctly, for
#: a conservative investor: it moved against the market.
BETA_SCALE = Scale(Decimal("1.5"), Decimal("0.5"))
SHARPE_SCALE = Scale(Decimal("-0.5"), Decimal("1.5"))

# -- Diversification --------------------------------------------------
#
# Both scales are inverted: the *less* of this asset and its sector the
# portfolio already holds, the more a new contribution diversifies. The
# ceilings are the concentration limits rule 32 asks for, expressed as
# the point where the pillar scores zero.

ASSET_WEIGHT_SCALE = Scale(Decimal("0.20"), Decimal(0))
SECTOR_WEIGHT_SCALE = Scale(Decimal("0.40"), Decimal(0))

#: Intended weight of each pillar in the final score.
#:
#: Quality and Risk lead at 0.25 because the investor is conservative:
#: what the business is and how much it swings matter more than whether
#: it is momentarily cheap. Growth is lightest at 0.15 — it is the most
#: extrapolative of the five.
PILLAR_WEIGHTS: dict[str, Decimal] = {
    "quality": Decimal("0.25"),
    "valuation": Decimal("0.20"),
    "growth": Decimal("0.15"),
    "risk": Decimal("0.25"),
    "diversification": Decimal("0.15"),
}


@dataclass(frozen=True)
class SubScore:
    """One pillar, with everything needed to explain it.

    `components` holds each contributing metric already mapped onto
    0-100, and `missing` names the inputs that were absent. Both are
    populated even when `value` is `None`, so "why could this not be
    computed" is answerable from the result alone.
    """

    name: str
    value: Decimal | None
    weight: Decimal
    components: dict[str, Decimal] = field(default_factory=dict)
    missing: tuple[str, ...] = ()

    @property
    def is_available(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class AssetScore:
    """The composed score for one asset.

    `coverage` is the fraction of `PILLAR_WEIGHTS` that was actually
    available. Two scores with different coverage are not comparable —
    see the module docstring.
    """

    formula_version: str
    sub_scores: tuple[SubScore, ...]
    final_score: Decimal | None
    coverage: Decimal

    @property
    def available(self) -> tuple[SubScore, ...]:
        return tuple(sub for sub in self.sub_scores if sub.is_available)


def score_quality(
    roe: Decimal | None = None,
    roic: Decimal | None = None,
    net_margin: Decimal | None = None,
) -> SubScore:
    """How good the business is at turning capital into profit.

    Averages whatever of ROE, ROIC and net margin is available. All three
    come from the income statement and the balance sheet, so in practice
    they are absent or present together.
    """
    return _average_pillar(
        "quality",
        {
            "roe": (roe, ROE_SCALE),
            "roic": (roic, ROIC_SCALE),
            "net_margin": (net_margin, NET_MARGIN_SCALE),
        },
    )


def score_valuation(pe: Decimal | None = None, pb: Decimal | None = None) -> SubScore:
    """How much is being paid for that business.

    A **non-positive multiple scores zero**, and does not reach the scale
    at all. Left to the clamp it would score 100, because a negative P/E
    is arithmetically lower than a cheap one — see the note above
    `PE_SCALE`. Zero is the honest reading: a company with negative
    earnings, or negative book equity, cannot be called cheap on that
    measure.

    Both inputs became computable in W09-003, when the share count
    started arriving per fiscal year from the CVM instead of as the
    vendor's present-day snapshot — applying today's count to an old
    balance sheet would have been look-ahead (rules 108/109). They are
    still absent for any filing whose share count could not be
    reconciled, and for every asset with no filing at all: an FII, an
    ETF or a BDR files no DFP, so this pillar is permanently absent for
    them rather than temporarily missing.
    """
    return _average_pillar(
        "valuation",
        {"pe": (pe, PE_SCALE), "pb": (pb, PB_SCALE)},
        positive_only=frozenset({"pe", "pb"}),
    )


def score_growth(
    revenue_growth: Decimal | None = None,
    profit_growth: Decimal | None = None,
) -> SubScore:
    """Whether the business is getting bigger, and more profitable.

    Revenue and profit growth are scored on the same symmetric scale, so
    a company growing revenue while losing money does not get to hide
    behind one of them.
    """
    return _average_pillar(
        "growth",
        {
            "revenue_growth": (revenue_growth, REVENUE_GROWTH_SCALE),
            "profit_growth": (profit_growth, PROFIT_GROWTH_SCALE),
        },
    )


def score_risk(
    series: list[PricePoint],
    benchmark: list[PricePoint] | None = None,
    risk_free_rate: Decimal | None = None,
    periodicity: Periodicity = Periodicity.DAILY,
    as_of: date | None = None,
) -> SubScore:
    """How much the investor is likely to suffer holding this.

    Built entirely on `app.quant` — volatility, maximum drawdown, beta
    and Sharpe. Nothing is recomputed here; this module only maps those
    numbers onto the conservative calibration above.

    `benchmark` and `risk_free_rate` come from Wave 08. Without them beta
    and Sharpe are absent and the pillar rests on volatility and drawdown
    alone, which is degraded but still meaningful — and `missing` says
    so.
    """
    drawdown = max_drawdown(series, as_of)
    return _average_pillar(
        "risk",
        {
            "volatility": (
                volatility(series, periodicity, as_of),
                VOLATILITY_SCALE,
            ),
            "max_drawdown": (
                drawdown.value if drawdown is not None else None,
                DRAWDOWN_SCALE,
            ),
            "beta": (beta(series, benchmark, periodicity, as_of), BETA_SCALE),
            "sharpe": (
                sharpe(series, risk_free_rate, periodicity, as_of),
                SHARPE_SCALE,
            ),
        },
    )


def score_diversification(
    asset_weight: Decimal | None = None,
    sector_weight: Decimal | None = None,
) -> SubScore:
    """How much room the portfolio still has for this asset.

    Both weights are fractions of the portfolio's invested value: how
    much of it is already this asset, and how much is already its sector.
    Lower means a contribution here spreads risk rather than piling it
    up (rule 32 — concentration limits).

    An empty portfolio yields weights of zero and therefore a score of
    100. That is honest rather than useful: with nothing held, every
    asset diversifies equally and this pillar cannot discriminate between
    them.

    `sector_weight` is `None` when the asset has no sector recorded, and
    the pillar then rests on the asset weight alone.
    """
    return _average_pillar(
        "diversification",
        {
            "asset_weight": (asset_weight, ASSET_WEIGHT_SCALE),
            "sector_weight": (sector_weight, SECTOR_WEIGHT_SCALE),
        },
    )


def compose(sub_scores: list[SubScore]) -> AssetScore:
    """Combine pillars into a final score, renormalising over what exists.

    `final_score` is `None` when fewer than `MIN_SUB_SCORES` pillars are
    available. `coverage` is reported either way — a score of `None` with
    a coverage of `0.15` says something quite different from `None` with
    a coverage of `0`.
    """
    ordered = tuple(sub_scores)
    available = [sub for sub in ordered if sub.is_available]

    intended = sum(PILLAR_WEIGHTS.values(), Decimal(0))
    covered = sum((sub.weight for sub in available), Decimal(0))
    coverage = covered / intended if intended else Decimal(0)

    if len(available) < MIN_SUB_SCORES or covered == 0:
        return AssetScore(
            formula_version=SCORING_FORMULA_VERSION,
            sub_scores=ordered,
            final_score=None,
            coverage=coverage,
        )

    weighted = sum(
        # `is_available` is what the filter above tested, so `value` is
        # not None here; the guard keeps the type checker honest.
        (sub.weight * sub.value for sub in available if sub.value is not None),
        Decimal(0),
    )
    return AssetScore(
        formula_version=SCORING_FORMULA_VERSION,
        sub_scores=ordered,
        final_score=weighted / covered,
        coverage=coverage,
    )


# -- helpers ---------------------------------------------------------


def _average_pillar(
    name: str,
    inputs: dict[str, tuple[Decimal | None, Scale]],
    positive_only: frozenset[str] = frozenset(),
) -> SubScore:
    """Map each input through its scale and average the survivors.

    An equal-weighted mean of the *available* components, not of all of
    them: a missing ROIC must not drag Quality down as though it were a
    ROIC of zero. That is the same rule the final score follows one level
    up, for the same reason.

    A metric named in `positive_only` scores the worst possible value
    when it is not strictly positive, instead of being put through the
    scale. Only the valuation multiples need this, and they need it
    badly: on an inverted scale a negative ratio clamps to the *best*
    end. Note this is a score of 0, not an absence — a negative P/E is a
    measurement, and a bad one.
    """
    components: dict[str, Decimal] = {}
    missing: list[str] = []

    for key, (raw, scale) in inputs.items():
        if raw is not None and key in positive_only and raw <= 0:
            components[key] = WORST
            continue
        scored = scale(raw)
        if scored is None:
            missing.append(key)
        else:
            components[key] = scored

    value = (
        sum(components.values(), Decimal(0)) / len(components) if components else None
    )
    return SubScore(
        name=name,
        value=value,
        weight=PILLAR_WEIGHTS[name],
        components=components,
        missing=tuple(missing),
    )
