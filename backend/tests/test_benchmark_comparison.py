"""Tests for the pure benchmark comparison.

Hand-computed expectations throughout. The comparison itself calculates
nothing — every figure comes from `app.quant` — so what is checked here
is the wiring, the normalisations, and the deliberate refusals.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.domain.benchmarks.catalog import CDI, IBOVESPA, IPCA
from app.domain.benchmarks.comparison import compare, summarise
from app.quant.returns import Periodicity, PricePoint


def _series(*levels: str, start_day: int = 1) -> list[PricePoint]:
    first = date(2026, 1, start_day)
    return [
        PricePoint(date=first + timedelta(days=offset), adjusted_close=Decimal(level))
        for offset, level in enumerate(levels)
    ]


# -- summarise -------------------------------------------------------


def test_summarise_reports_the_window_it_actually_measured():
    performance = summarise(_series("100", "110", "120"))

    assert performance.start_date == date(2026, 1, 1)
    assert performance.end_date == date(2026, 1, 3)
    assert performance.observations == 3
    assert performance.total_return == Decimal("0.2")


def test_summarise_reports_a_drawdown_of_zero_for_a_series_that_only_rose():
    """Zero is a measurement here, not a missing value."""
    performance = summarise(_series("100", "110", "120"))

    assert performance.max_drawdown == Decimal(0)


def test_summarise_reports_the_deepest_fall_below_a_running_peak():
    performance = summarise(_series("100", "120", "90"))

    assert performance.max_drawdown == Decimal("-0.25")


def test_summarise_of_an_empty_series_reports_nothing_rather_than_zero():
    performance = summarise([])

    assert performance.start_date is None
    assert performance.observations == 0
    assert performance.total_return is None
    assert performance.max_drawdown is None


def test_summarise_carries_the_periodicity_it_annualised_on():
    performance = summarise(_series("100", "110"), Periodicity.MONTHLY)

    assert performance.periodicity is Periodicity.MONTHLY


# -- the comparison --------------------------------------------------


def test_excess_return_is_a_difference_in_fraction_points():
    """+20% against +5% is 15 percentage points, not 4x."""
    result = compare(_series("100", "120"), _series("100", "105"), IBOVESPA)

    assert result.subject.total_return == Decimal("0.2")
    assert result.benchmark.total_return == Decimal("0.05")
    assert result.excess_return == Decimal("0.15")


def test_return_ratio_is_the_multiple_a_brazilian_investor_reads():
    """+11.5% against a +10% CDI is "115% do CDI"."""
    result = compare(_series("100", "111.5"), _series("100", "110"), CDI)

    assert result.return_ratio == Decimal("1.15")


def test_return_ratio_is_withheld_when_the_benchmark_fell():
    """A ratio inverts its own meaning against a negative benchmark.

    Down 5% while the index fell 10% would read as "50% of the
    benchmark", which sounds like underperformance and is the opposite of
    what happened. The excess return stays correct and is what to read.
    """
    result = compare(_series("100", "95"), _series("100", "90"), IBOVESPA)

    assert result.return_ratio is None
    assert result.excess_return == Decimal("0.05")


def test_return_ratio_is_withheld_when_the_benchmark_did_not_move():
    result = compare(_series("100", "120"), _series("100", "100"), IBOVESPA)

    assert result.return_ratio is None


def test_return_ratio_is_withheld_when_the_subject_lost_money():
    """ "-180% do CDI" is not a phrase that means anything.

    Found on real data: the Ibovespa fell 5.96% over a quarter in which
    the CDI earned 3.32%, and the ratio came out at -1.80. The excess
    return of -9.28 percentage points says the same thing without
    inviting the reader to parse a negative multiple.
    """
    result = compare(_series("100", "94.04"), _series("100", "103.32"), CDI)

    assert result.return_ratio is None
    assert result.excess_return == Decimal("-0.0928")


def test_return_ratio_is_withheld_against_a_benchmark_that_barely_moved():
    """A near-zero denominator explodes into a number that is not a fact.

    Also from real data: against an IPCA of +0.07% over the window, a
    6% fall reported as a ratio of -85.
    """
    result = compare(_series("100", "94.04"), _series("100", "100.07"), IPCA)

    assert result.return_ratio is None


def test_beta_is_reported_against_an_index():
    """An asset moving twice the index, measured over the same dates."""
    subject = _series("100", "120", "96")
    benchmark = _series("100", "110", "99")

    result = compare(subject, benchmark, IBOVESPA)

    assert result.beta == Decimal(2)


def test_beta_is_refused_against_a_rate_benchmark():
    """Sensitivity to the CDI is not a quantity that means anything.

    And it would not come back as `None` on its own: the CDI's variance
    is tiny but not exactly zero, so the guard inside `beta` never fires
    and a huge, unstable number would be reported with a straight face.
    Refusing it here is the only place that can.
    """
    subject = _series("100", "120", "96")
    cdi = _series("100", "100.0004", "100.0008")

    result = compare(subject, cdi, CDI)

    assert result.beta is None


def test_sharpe_and_sortino_need_a_risk_free_rate():
    """Without the CDI they stay `None`, never computed against zero.

    A zero risk-free rate flatters every asset, and in Brazil it is not
    remotely close to the truth.
    """
    subject = _series("100", "102", "101", "104")

    without = compare(subject, _series("100", "101"), IBOVESPA)
    with_rate = compare(
        subject, _series("100", "101"), IBOVESPA, risk_free_rate=Decimal("0.1075")
    )

    assert without.sharpe is None
    assert without.sortino is None
    assert with_rate.sharpe is not None
    assert with_rate.sortino is not None
    assert with_rate.risk_free_rate == Decimal("0.1075")


def test_the_benchmark_is_measured_at_its_own_periodicity():
    """A monthly benchmark is not pretended to be daily."""
    result = compare(_series("100", "110"), _series("100", "101"), CDI)
    assert result.benchmark.periodicity is Periodicity.DAILY

    monthly = compare(_series("100", "110"), _series("100", "101"), IPCA)
    assert monthly.benchmark.periodicity is Periodicity.MONTHLY
    assert monthly.subject.periodicity is Periodicity.DAILY


def test_the_benchmark_identity_is_carried_through():
    result = compare(_series("100", "110"), _series("100", "101"), CDI)

    assert result.benchmark_code == "CDI"
    assert result.benchmark_name == CDI.name


def test_a_comparison_without_a_benchmark_series_still_reports_the_subject():
    """Nothing ingested yet is missing data, not an error."""
    result = compare(_series("100", "120"), [], IBOVESPA)

    assert result.subject.total_return == Decimal("0.2")
    assert result.benchmark.total_return is None
    assert result.excess_return is None
    assert result.return_ratio is None
    assert result.beta is None


def test_nothing_after_as_of_is_read():
    subject = _series("100", "110", "120")

    result = compare(
        subject, _series("100", "101", "102"), IBOVESPA, as_of=date(2026, 1, 2)
    )

    assert result.subject.end_date == date(2026, 1, 2)
    assert result.subject.total_return == Decimal("0.1")
