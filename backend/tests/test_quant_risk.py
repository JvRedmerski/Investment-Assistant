"""Unit tests for app.quant.risk (AGENTS.md rule 68: known input -> known
expected output, worked out by hand).

Series are built so the statistics land on exact decimal values. The
recurring price path 100 -> 110 -> 110 -> 99 gives returns
[+0.1, 0, -0.1], whose mean is 0 and whose sample standard deviation is
exactly 0.1: sum of squares 0.02, divided by n-1 = 2, square root of 0.01.
That lets every assertion be an equality against a number computed by
hand, with the annualisation factor left visible as `sqrt(252)` rather
than a decimal literal nobody can check.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.quant.returns import DAYS_PER_YEAR, Periodicity, PricePoint
from app.quant.risk import (
    MIN_OBSERVATIONS,
    PERIODS_PER_YEAR,
    beta,
    downside_deviation,
    max_drawdown,
    sharpe,
    sortino,
    standard_deviation,
    volatility,
)

SQRT_252 = Decimal(252).sqrt()


def _series(*prices: str, start_day: int = 5) -> list[PricePoint]:
    """Consecutive daily observations from 2026-01-`start_day`."""
    return [
        PricePoint(
            date=date(2026, 1, start_day + offset), adjusted_close=Decimal(price)
        )
        for offset, price in enumerate(prices)
    ]


def _yearly(*pairs: tuple[int, str]) -> list[PricePoint]:
    return [
        PricePoint(date=date(year, 12, 31), adjusted_close=Decimal(price))
        for year, price in pairs
    ]


#: returns [+0.1, 0, -0.1]: mean 0, sample stdev exactly 0.1
FLAT_MEAN_SERIES = _series("100", "110", "110", "99")

#: returns [+0.2, +0.1, 0]: mean 0.1, sample stdev exactly 0.1
RISING_SERIES = _series("100", "120", "132", "132")

#: returns [+0.5, -0.1, -0.1]: mean 0.1, downside deviation exactly 0.1,
#: total stdev much larger — the dispersion is mostly the upside jump
UPSIDE_JUMP_SERIES = _series("100", "150", "135", "121.5")


# -- the ADR-017 constraint ------------------------------------------


def test_dispersion_annualises_on_trading_sessions_not_calendar_days():
    """Guards the constraint ADR-017 exists to protect.

    Dispersion scales with the number of observations, so it annualises on
    ~252 sessions; compound return scales with elapsed time, so it
    annualises on 365 calendar days. Reusing `DAYS_PER_YEAR` here would
    inflate volatility by sqrt(365/252) ~ 1.2 and push the same error into
    every Sharpe ratio, with nothing in the output to show it.
    """
    assert PERIODS_PER_YEAR[Periodicity.DAILY] == 252
    assert PERIODS_PER_YEAR[Periodicity.DAILY] != DAYS_PER_YEAR


def test_periods_per_year_covers_every_periodicity():
    # A missing entry would raise KeyError deep inside a metric.
    assert set(PERIODS_PER_YEAR) == set(Periodicity)


# -- standard_deviation ----------------------------------------------


def test_standard_deviation_of_a_known_sample():
    # [0.1, 0, -0.1]: mean 0, sum of squares 0.02, /(3-1) = 0.01, sqrt 0.1
    values = [Decimal("0.1"), Decimal(0), Decimal("-0.1")]

    assert standard_deviation(values) == Decimal("0.1")


def test_standard_deviation_uses_the_sample_form_not_the_population_form():
    """Bessel's correction: dividing by n would give a smaller number.

    [1, -1]: mean 0, sum of squares 2. Sample form -> 2/1 = 2, sqrt(2).
    Population form -> 2/2 = 1, sqrt(1) = 1. The result must be sqrt(2).
    """
    values = [Decimal(1), Decimal(-1)]

    assert standard_deviation(values) == Decimal(2).sqrt()
    assert standard_deviation(values) != Decimal(1)


def test_standard_deviation_of_identical_values_is_a_real_zero():
    values = [Decimal("0.05"), Decimal("0.05"), Decimal("0.05")]

    result = standard_deviation(values)

    assert result == 0
    assert result is not None


@pytest.mark.parametrize("values", [[], [Decimal("0.1")]])
def test_standard_deviation_needs_at_least_two_observations(values):
    assert len(values) < MIN_OBSERVATIONS
    assert standard_deviation(values) is None


# -- downside_deviation ----------------------------------------------


def test_downside_deviation_of_a_known_sample():
    # Two shortfalls of -0.1 among three observations:
    # sum of squares 0.02, /(3-1) = 0.01, sqrt 0.1
    values = [Decimal("0.5"), Decimal("-0.1"), Decimal("-0.1")]

    assert downside_deviation(values, Decimal(0)) == Decimal("0.1")


def test_downside_deviation_ignores_upside_dispersion():
    """Replacing the upside value changes stdev but not downside deviation."""
    modest = [Decimal("0.5"), Decimal("-0.1"), Decimal("-0.1")]
    violent = [Decimal("5.0"), Decimal("-0.1"), Decimal("-0.1")]

    assert downside_deviation(modest, Decimal(0)) == downside_deviation(
        violent, Decimal(0)
    )
    assert standard_deviation(modest) != standard_deviation(violent)


def test_downside_deviation_divides_by_all_observations_not_just_shortfalls():
    """The original Sortino denominator counts every observation.

    One shortfall of -0.2 among three: sum of squares 0.04, divided by
    n-1 = 2, giving 0.02 and sqrt(0.02). Counting only the single shortfall
    would divide by 0 or 1 and report a larger downside risk for an asset
    whose losses are rarer — inverting the meaning.
    """
    values = [Decimal("0.1"), Decimal("0.1"), Decimal("-0.2")]

    assert downside_deviation(values, Decimal(0)) == Decimal("0.02").sqrt()


def test_downside_deviation_is_none_when_nothing_fell_below_target():
    # Not zero risk: a sample with no downside carries no evidence about
    # downside, and zero here would make Sortino look infinitely good.
    values = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]

    assert downside_deviation(values, Decimal(0)) is None


def test_downside_deviation_respects_a_non_zero_target():
    # Target 0.15: shortfalls are 0.1 and 0.2 -> -0.05 and +0.05, so only
    # the first counts. Sum of squares 0.0025, /(2-1) = 0.0025, sqrt 0.05
    values = [Decimal("0.1"), Decimal("0.2")]

    assert downside_deviation(values, Decimal("0.15")) == Decimal("0.05")


# -- volatility ------------------------------------------------------


def test_volatility_annualises_the_periodic_deviation():
    # Periodic stdev is exactly 0.1; annualised is 0.1 * sqrt(252).
    result = volatility(FLAT_MEAN_SERIES)

    assert result == Decimal("0.1") * SQRT_252


def test_volatility_can_be_reported_per_period():
    assert volatility(FLAT_MEAN_SERIES, annualised=False) == Decimal("0.1")


def test_volatility_of_a_flat_series_is_a_real_zero():
    result = volatility(_series("100", "100", "100"))

    assert result == 0
    assert result is not None


def test_volatility_scales_by_the_factor_of_the_requested_periodicity():
    """Monthly observations annualise on 12, not 252."""
    monthly = [
        PricePoint(date=date(2026, month, 28), adjusted_close=Decimal(price))
        for month, price in ((1, "100"), (2, "110"), (3, "110"), (4, "99"))
    ]

    result = volatility(monthly, Periodicity.MONTHLY)

    assert result == Decimal("0.1") * Decimal(12).sqrt()


def test_volatility_ignores_observations_after_as_of():
    series = _series("100", "110", "110", "99", "1000")

    assert volatility(series, as_of=date(2026, 1, 8)) == Decimal("0.1") * SQRT_252


@pytest.mark.parametrize("series", [[], _series("100"), _series("100", "110")])
def test_volatility_needs_at_least_two_returns(series):
    # Two prices give one return, which is not a sample to estimate from.
    assert volatility(series) is None


def test_volatility_tolerates_a_gap_in_the_series():
    """Gaps are normal (ADR-016) and must not crash or be special-cased."""
    series = [
        PricePoint(date=date(2026, 1, 5), adjusted_close=Decimal(100)),
        PricePoint(date=date(2026, 1, 6), adjusted_close=Decimal(110)),
        # 2026-01-07 absent: its adjustment was never published.
        PricePoint(date=date(2026, 1, 8), adjusted_close=Decimal(110)),
        PricePoint(date=date(2026, 1, 9), adjusted_close=Decimal(99)),
    ]

    assert volatility(series) == Decimal("0.1") * SQRT_252


# -- max_drawdown ----------------------------------------------------


def test_max_drawdown_of_a_known_path():
    # Peak 120, trough 60: 60/120 - 1 = -0.5. The later decline to 80
    # (-0.333 from the same peak) is shallower and must not win.
    series = _series("100", "120", "60", "80")

    result = max_drawdown(series)

    assert result is not None
    assert result.value == Decimal("-0.5")
    assert result.peak_date == date(2026, 1, 6)
    assert result.peak_price == Decimal(120)
    assert result.trough_date == date(2026, 1, 7)
    assert result.trough_price == Decimal(60)


def test_max_drawdown_is_reported_as_a_negative_fraction():
    result = max_drawdown(_series("100", "75"))

    assert result is not None
    assert result.value == Decimal("-0.25")
    assert result.value < 0


def test_max_drawdown_measures_from_the_running_peak_not_the_first_price():
    """A new high resets the peak, so a later fall is measured from it.

    Falling 100 -> 90 is -10%; then rising to 200 and falling to 150 is
    -25% from the new peak. Measuring everything from the opening price
    would report the second trough as +50% and miss the drawdown entirely.
    """
    series = _series("100", "90", "200", "150")

    result = max_drawdown(series)

    assert result is not None
    assert result.value == Decimal("-0.25")
    assert result.peak_price == Decimal(200)


def test_max_drawdown_of_a_monotonically_rising_series_is_a_real_zero():
    # A real measurement: the price never sat below a previous peak.
    result = max_drawdown(_series("100", "110", "120"))

    assert result is not None
    assert result.value == Decimal(0)


def test_max_drawdown_ignores_observations_after_as_of():
    series = _series("100", "120", "60", "80", "1")

    result = max_drawdown(series, as_of=date(2026, 1, 8))

    assert result is not None
    assert result.value == Decimal("-0.5")


@pytest.mark.parametrize("series", [[], _series("100")])
def test_max_drawdown_needs_at_least_two_observations(series):
    assert max_drawdown(series) is None


# -- beta ------------------------------------------------------------


def test_beta_of_an_asset_moving_twice_the_benchmark():
    # Benchmark returns [+0.1, -0.1], asset returns [+0.2, -0.2].
    # cov = 0.2*0.1 + (-0.2)*(-0.1) = 0.04; var = 0.01 + 0.01 = 0.02.
    benchmark = _series("100", "110", "99")
    asset = _series("100", "120", "96")

    assert beta(asset, benchmark) == Decimal(2)


def test_beta_against_itself_is_one():
    series = _series("100", "110", "99", "108.9")

    assert beta(series, series) == Decimal(1)


def test_beta_is_negative_when_the_asset_moves_inversely():
    benchmark = _series("100", "110", "99")
    asset = _series("100", "90", "99")

    result = beta(asset, benchmark)

    assert result is not None
    assert result < 0


def test_beta_aligns_the_two_series_on_shared_dates_before_measuring():
    """The trap that makes `beta` take prices instead of return series.

    The asset is missing 2026-01-07, so its second return spans 01-06 to
    01-08. The benchmark has that date, so pairing by position would
    regress the asset's two-day interval against the benchmark's 01-06 to
    01-07 — a different interval, and here a wildly different move.

    Restricted to the three shared dates, both series follow the identical
    path 100 -> 110 -> 99, so beta must be exactly 1. Any other value means
    2026-01-07 leaked in.
    """
    asset = [
        PricePoint(date=date(2026, 1, 5), adjusted_close=Decimal(100)),
        PricePoint(date=date(2026, 1, 6), adjusted_close=Decimal(110)),
        PricePoint(date=date(2026, 1, 8), adjusted_close=Decimal(99)),
    ]
    benchmark = [
        PricePoint(date=date(2026, 1, 5), adjusted_close=Decimal(100)),
        PricePoint(date=date(2026, 1, 6), adjusted_close=Decimal(110)),
        PricePoint(date=date(2026, 1, 7), adjusted_close=Decimal(200)),
        PricePoint(date=date(2026, 1, 8), adjusted_close=Decimal(99)),
    ]

    assert beta(asset, benchmark) == Decimal(1)


def test_beta_is_none_without_a_benchmark():
    # The Wave 08 dependency: no CDI/IBOV series exists yet, and the
    # answer is "not computable" rather than a fabricated 1.
    series = _series("100", "110", "99")

    assert beta(series) is None
    assert beta(series, None) is None
    assert beta(series, []) is None


def test_beta_is_none_when_the_benchmark_never_moved():
    # Zero variance leaves the sensitivity undefined, not infinite.
    asset = _series("100", "110", "99")
    benchmark = _series("100", "100", "100")

    assert beta(asset, benchmark) is None


def test_beta_is_none_when_too_few_dates_are_shared():
    asset = _series("100", "110", "99", start_day=5)
    benchmark = _series("100", "110", "99", start_day=20)

    assert beta(asset, benchmark) is None


def test_beta_ignores_observations_after_as_of():
    asset = _series("100", "120", "96", "1000")
    benchmark = _series("100", "110", "99", "1000")

    assert beta(asset, benchmark, as_of=date(2026, 1, 7)) == Decimal(2)


# -- sharpe ----------------------------------------------------------


def test_sharpe_of_a_known_series_at_a_zero_risk_free_rate():
    # Returns [0.2, 0.1, 0]: mean 0.1, sample stdev 0.1, ratio 1.
    # Annualised: 1 * sqrt(252).
    result = sharpe(RISING_SERIES, risk_free_rate=Decimal(0))

    assert result == SQRT_252


def test_a_higher_risk_free_rate_lowers_sharpe():
    low = sharpe(RISING_SERIES, risk_free_rate=Decimal(0))
    high = sharpe(RISING_SERIES, risk_free_rate=Decimal("0.15"))

    assert low is not None and high is not None
    assert high < low


def test_sharpe_goes_negative_when_the_asset_underperforms_the_rate():
    """Yearly returns [+0.3, +0.1] against a 50% annual rate.

    Stated at yearly periodicity because that is where the annual rate and
    the periodic rate coincide, so the comparison is legible. Excess is
    [-0.2, -0.4], whose mean is -0.3, so the ratio is negative.

    Note how easy it would be to write this test wrongly at daily
    periodicity: a 200% *annual* rate de-annualises to about 0.44% *a day*,
    which is far below this series' 10%-a-day mean, so Sharpe would stay
    firmly positive. That is the geometric conversion behaving correctly,
    not a bug.
    """
    series = _yearly((2023, "100"), (2024, "130"), (2025, "143"))

    result = sharpe(
        series, risk_free_rate=Decimal("0.5"), periodicity=Periodicity.YEARLY
    )

    assert result is not None
    assert result < 0
    assert result == Decimal("-0.3") / Decimal("0.02").sqrt()


def test_sharpe_de_annualises_the_rate_geometrically():
    """At yearly periodicity the periodic rate equals the annual rate.

    Yearly returns [+0.3, +0.1] against an annual 10% rate leave excess
    [+0.2, 0]: mean 0.1, sample stdev sqrt(0.02). The ratio is
    0.1 / sqrt(0.02) = 1 / sqrt(2), and sqrt(1) leaves it unscaled.

    This pins the rate conversion where it is exactly checkable; for daily
    periodicity the same code raises (1 + rate) to the 1/252, which is
    compounding rather than a division by 252.
    """
    series = _yearly((2023, "100"), (2024, "130"), (2025, "143"))

    result = sharpe(
        series, risk_free_rate=Decimal("0.1"), periodicity=Periodicity.YEARLY
    )

    assert result == pytest.approx(Decimal(1) / Decimal(2).sqrt(), abs=Decimal("1e-25"))


def test_sharpe_is_none_without_a_risk_free_rate():
    # The Wave 08 dependency: assuming zero would flatter every asset.
    assert sharpe(RISING_SERIES) is None
    assert sharpe(RISING_SERIES, risk_free_rate=None) is None


def test_sharpe_is_none_when_there_is_no_dispersion():
    # Zero volatility leaves risk-adjusted return undefined, not infinite.
    flat = _series("100", "100", "100")

    assert sharpe(flat, risk_free_rate=Decimal(0)) is None


@pytest.mark.parametrize("series", [[], _series("100"), _series("100", "110")])
def test_sharpe_needs_at_least_two_returns(series):
    assert sharpe(series, risk_free_rate=Decimal(0)) is None


def test_sharpe_ignores_observations_after_as_of():
    series = _series("100", "120", "132", "132", "10000")

    result = sharpe(series, risk_free_rate=Decimal(0), as_of=date(2026, 1, 8))

    assert result == SQRT_252


# -- sortino ---------------------------------------------------------


def test_sortino_of_a_known_series_at_a_zero_risk_free_rate():
    # Returns [+0.5, -0.1, -0.1]: mean 0.1, downside deviation 0.1,
    # ratio 1, annualised 1 * sqrt(252).
    result = sortino(UPSIDE_JUMP_SERIES, risk_free_rate=Decimal(0))

    assert result == SQRT_252


def test_sortino_exceeds_sharpe_when_dispersion_is_mostly_upside():
    """The whole point of the ratio.

    The +50% jump dominates the standard deviation, so Sharpe penalises it;
    downside deviation ignores it, so Sortino does not.
    """
    sharpe_value = sharpe(UPSIDE_JUMP_SERIES, risk_free_rate=Decimal(0))
    sortino_value = sortino(UPSIDE_JUMP_SERIES, risk_free_rate=Decimal(0))

    assert sharpe_value is not None and sortino_value is not None
    assert sortino_value > sharpe_value


def test_sortino_is_none_when_no_period_fell_short_of_the_rate():
    # RISING_SERIES returns [0.2, 0.1, 0] are all >= 0, so there is no
    # downside evidence. Reporting a number here would look flawless.
    assert sortino(RISING_SERIES, risk_free_rate=Decimal(0)) is None


def test_sortino_is_none_without_a_risk_free_rate():
    assert sortino(UPSIDE_JUMP_SERIES) is None


@pytest.mark.parametrize("series", [[], _series("100"), _series("100", "90")])
def test_sortino_needs_at_least_two_returns(series):
    assert sortino(series, risk_free_rate=Decimal(0)) is None


def test_sortino_ignores_observations_after_as_of():
    series = _series("100", "150", "135", "121.5", "10000")

    result = sortino(series, risk_free_rate=Decimal(0), as_of=date(2026, 1, 8))

    assert result == SQRT_252
