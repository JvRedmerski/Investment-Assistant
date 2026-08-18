"""Tests for the asset sub-scores.

Pure function, hand-computed expectations (AGENTS.md rule 68). Every
number below was worked out from the constants in `scoring.py`, not read
back from the code — which is how the negative-P/E inversion was caught
while these were being written.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.recommendations.scoring import (
    MIN_SUB_SCORES,
    PILLAR_WEIGHTS,
    SCORING_FORMULA_VERSION,
    Scale,
    SubScore,
    compose,
    score_diversification,
    score_growth,
    score_quality,
    score_risk,
    score_valuation,
)
from app.quant.returns import PricePoint


def _series(*levels: str, start_day: int = 1) -> list[PricePoint]:
    first = date(2026, 1, start_day)
    return [
        PricePoint(date=first + timedelta(days=offset), adjusted_close=Decimal(level))
        for offset, level in enumerate(levels)
    ]


# -- the scale primitive ---------------------------------------------


def test_a_scale_maps_linearly_between_its_calibration_points():
    scale = Scale(Decimal(0), Decimal(10))

    assert scale(Decimal(0)) == Decimal(0)
    assert scale(Decimal(5)) == Decimal(50)
    assert scale(Decimal(10)) == Decimal(100)


def test_a_scale_clamps_at_both_ends():
    """80% ROE does not deserve 400 points."""
    scale = Scale(Decimal(0), Decimal(10))

    assert scale(Decimal(-5)) == Decimal(0)
    assert scale(Decimal(40)) == Decimal(100)


def test_an_inverted_scale_scores_a_lower_value_higher():
    scale = Scale(Decimal(25), Decimal(5))

    assert scale(Decimal(25)) == Decimal(0)
    assert scale(Decimal(15)) == Decimal(50)
    assert scale(Decimal(5)) == Decimal(100)


def test_a_scale_passes_absence_through():
    assert Scale(Decimal(0), Decimal(10))(None) is None


# -- quality ----------------------------------------------------------


def test_quality_averages_its_available_components():
    """ROE 10%/20% = 50, ROIC 7.5%/15% = 50, margin 5%/20% = 25.

    Mean of 50, 50 and 25 is 125/3.
    """
    pillar = score_quality(
        roe=Decimal("0.10"), roic=Decimal("0.075"), net_margin=Decimal("0.05")
    )

    assert pillar.components == {
        "roe": Decimal(50),
        "roic": Decimal(50),
        "net_margin": Decimal(25),
    }
    assert pillar.value == Decimal(125) / Decimal(3)
    assert pillar.missing == ()


def test_a_missing_component_is_left_out_rather_than_scored_zero():
    """A missing ROIC must not drag Quality down as though it were 0%."""
    pillar = score_quality(roe=Decimal("0.20"), net_margin=Decimal("0.20"))

    assert pillar.value == Decimal(100)
    assert pillar.missing == ("roic",)


def test_quality_is_absent_when_nothing_is_known():
    pillar = score_quality()

    assert pillar.value is None
    assert pillar.is_available is False
    assert set(pillar.missing) == {"roe", "roic", "net_margin"}


def test_a_loss_making_company_scores_zero_on_quality_not_absent():
    """Negative ROE is a measurement, and a bad one — not missing data."""
    pillar = score_quality(roe=Decimal("-0.30"), roic=Decimal("-0.20"))

    assert pillar.value == Decimal(0)
    assert pillar.missing == ("net_margin",)


# -- valuation, and the inversion trap --------------------------------


def test_valuation_scores_a_cheaper_multiple_higher():
    """P/E 15 sits halfway between 25 (score 0) and 5 (score 100)."""
    pillar = score_valuation(pe=Decimal(15), pb=Decimal("2.25"))

    assert pillar.components["pe"] == Decimal(50)
    # P/B 2.25 between 4 and 0.5: (2.25 - 4) / (0.5 - 4) = 0.5.
    assert pillar.components["pb"] == Decimal(50)
    assert pillar.value == Decimal(50)


@pytest.mark.parametrize("pe", [Decimal(0), Decimal(-3), Decimal(-100)])
def test_a_non_positive_price_earnings_scores_zero_and_not_one_hundred(pe):
    """The trap the scale alone walks into.

    A negative P/E is arithmetically *lower* than a cheap one, so on the
    inverted scale it clamps to the best end and would score 100 — a
    company that lost money ranked as the cheapest on the exchange. It
    has to be floored explicitly, and it is a score of 0 rather than an
    absence, because a loss is a measurement.
    """
    pillar = score_valuation(pe=pe)

    assert pillar.components["pe"] == Decimal(0)
    assert pillar.value == Decimal(0)
    assert "pe" not in pillar.missing


def test_a_negative_book_value_scores_zero_on_price_to_book():
    pillar = score_valuation(pb=Decimal("-1.5"))

    assert pillar.value == Decimal(0)


def test_valuation_is_absent_without_multiples():
    """The state the project is actually in: the source stopped serving them."""
    pillar = score_valuation()

    assert pillar.value is None
    assert set(pillar.missing) == {"pe", "pb"}


# -- growth -----------------------------------------------------------


def test_flat_growth_scores_the_middle_rather_than_zero():
    """A company that is not growing is not thereby failing.

    The scale runs -20% to +20%, so 0% lands at 50.
    """
    pillar = score_growth(revenue_growth=Decimal(0), profit_growth=Decimal(0))

    assert pillar.value == Decimal(50)


def test_shrinking_and_growing_sit_on_opposite_sides_of_the_middle():
    shrinking = score_growth(revenue_growth=Decimal("-0.20"))
    growing = score_growth(revenue_growth=Decimal("0.20"))

    assert shrinking.value == Decimal(0)
    assert growing.value == Decimal(100)


def test_growing_revenue_while_losing_money_cannot_hide_behind_one_metric():
    """Both metrics score on the same scale, so the average tells on it."""
    pillar = score_growth(
        revenue_growth=Decimal("0.20"), profit_growth=Decimal("-0.20")
    )

    assert pillar.value == Decimal(50)


# -- risk -------------------------------------------------------------


def test_risk_rests_on_volatility_and_drawdown_without_a_benchmark():
    """Beta and Sharpe need Wave 08 data; their absence is reported."""
    pillar = score_risk(_series("100", "110", "99"))

    assert set(pillar.missing) == {"beta", "sharpe"}
    assert "volatility" in pillar.components
    assert "max_drawdown" in pillar.components
    assert pillar.is_available


def test_a_series_that_never_fell_scores_full_marks_on_drawdown():
    pillar = score_risk(_series("100", "110", "120"))

    assert pillar.components["max_drawdown"] == Decimal(100)


def test_a_deep_drawdown_scores_zero():
    """Down 60% from the peak is past the -50% floor of the scale."""
    pillar = score_risk(_series("100", "40"))

    assert pillar.components["max_drawdown"] == Decimal(0)


def test_beta_appears_once_a_benchmark_is_supplied():
    """An asset moving with the market scores mid-range on beta.

    Beta 1.0 sits halfway between 1.5 (score 0) and 0.5 (score 100).
    """
    subject = _series("100", "110", "99")
    benchmark = _series("100", "110", "99")

    pillar = score_risk(subject, benchmark=benchmark)

    assert pillar.components["beta"] == Decimal(50)
    assert "beta" not in pillar.missing


def test_an_asset_that_moves_against_the_market_scores_full_marks_on_beta():
    """A negative beta is a hedge, which a conservative profile wants."""
    subject = _series("100", "90", "101")
    benchmark = _series("100", "110", "99")

    pillar = score_risk(subject, benchmark=benchmark)

    assert pillar.components["beta"] == Decimal(100)


def test_risk_is_absent_when_the_series_is_too_short_to_measure():
    pillar = score_risk(_series("100"))

    assert pillar.value is None
    assert set(pillar.missing) == {"volatility", "max_drawdown", "beta", "sharpe"}


# -- diversification --------------------------------------------------


def test_an_empty_portfolio_leaves_maximum_room():
    pillar = score_diversification(asset_weight=Decimal(0), sector_weight=Decimal(0))

    assert pillar.value == Decimal(100)


def test_a_position_at_the_concentration_limit_scores_zero():
    """20% in one asset and 40% in one sector are the rule 32 ceilings."""
    pillar = score_diversification(
        asset_weight=Decimal("0.20"), sector_weight=Decimal("0.40")
    )

    assert pillar.value == Decimal(0)


def test_exceeding_the_limit_does_not_score_below_zero():
    pillar = score_diversification(asset_weight=Decimal("0.50"))

    assert pillar.value == Decimal(0)


def test_a_half_filled_position_scores_the_middle():
    pillar = score_diversification(
        asset_weight=Decimal("0.10"), sector_weight=Decimal("0.20")
    )

    assert pillar.value == Decimal(50)


def test_an_asset_without_a_sector_rests_on_its_own_weight():
    pillar = score_diversification(asset_weight=Decimal("0.10"))

    assert pillar.value == Decimal(50)
    assert pillar.missing == ("sector_weight",)


# -- composition ------------------------------------------------------


def _pillar(name: str, value) -> SubScore:
    return SubScore(
        name=name,
        value=None if value is None else Decimal(value),
        weight=PILLAR_WEIGHTS[name],
    )


def test_the_final_score_is_the_weighted_mean_of_every_pillar():
    """All five available at 60 must compose to exactly 60."""
    score = compose([_pillar(name, 60) for name in PILLAR_WEIGHTS])

    assert score.final_score == Decimal(60)
    assert score.coverage == Decimal(1)


def test_the_weights_are_renormalised_over_what_is_available():
    """Quality 80 at 0.25 and Risk 40 at 0.25 must average to 60.

    Not to 30, which is what leaving the missing weight in the
    denominator would give.
    """
    score = compose([_pillar("quality", 80), _pillar("risk", 40)])

    assert score.final_score == Decimal(60)


def test_coverage_reports_how_much_of_the_formula_the_score_rests_on():
    """Risk 0.25 plus Diversification 0.15 is 40% of the intended formula.

    This is the project's actual situation while the fundamentals source
    is unavailable, and the number is what stops the result being read as
    a full score.
    """
    score = compose(
        [
            _pillar("quality", None),
            _pillar("valuation", None),
            _pillar("growth", None),
            _pillar("risk", 70),
            _pillar("diversification", 50),
        ]
    )

    assert score.coverage == Decimal("0.40")
    # (0.25 * 70 + 0.15 * 50) / 0.40 = 25 / 0.40 = 62.5
    assert score.final_score == Decimal("62.5")


def test_a_single_pillar_does_not_make_a_final_score():
    """A composite of one is that one wearing a different name."""
    score = compose([_pillar("risk", 70)])

    assert score.final_score is None
    assert score.coverage == Decimal("0.25")


def test_no_pillars_at_all_yields_no_score_and_no_coverage():
    score = compose([_pillar(name, None) for name in PILLAR_WEIGHTS])

    assert score.final_score is None
    assert score.coverage == Decimal(0)


def test_a_missing_pillar_never_counts_as_zero():
    """The whole point: absence must not read as "bad".

    Quality 80 with everything else missing scores the same as Quality 80
    beside one other pillar of 80 — it does not get averaged down towards
    zero by the three that are absent.
    """
    with_absences = compose([_pillar("quality", 80), _pillar("risk", 80)])

    assert with_absences.final_score == Decimal(80)


def test_the_formula_version_travels_with_the_score():
    """Rule 30: a stored score must be traceable to its formula."""
    score = compose([_pillar("quality", 80), _pillar("risk", 40)])

    assert score.final_score is not None
    assert score.formula_version == SCORING_FORMULA_VERSION


def test_the_pillar_weights_add_up_to_one():
    assert sum(PILLAR_WEIGHTS.values(), Decimal(0)) == Decimal(1)


def test_the_available_pillars_are_exposed_for_explanation():
    score = compose(
        [_pillar("quality", 80), _pillar("risk", 40), _pillar("growth", None)]
    )

    assert len(score.sub_scores) == 3
    assert {sub.name for sub in score.available} == {"quality", "risk"}
    assert len(score.available) >= MIN_SUB_SCORES
