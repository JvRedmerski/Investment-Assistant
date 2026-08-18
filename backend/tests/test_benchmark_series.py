"""Tests for turning a stored benchmark series into a level series.

Every expected value is worked out by hand, not read back from the code.
"""

from datetime import date
from decimal import Decimal

from app.data.models.benchmarks import BenchmarkValue
from app.domain.benchmarks.catalog import CDI, IBOVESPA, IPCA
from app.domain.benchmarks.series import annualised_rate, to_price_points
from app.quant.returns import total_return
from app.quant.risk import _periodic_rate


def _value(day: date, amount: str) -> BenchmarkValue:
    return BenchmarkValue(
        benchmark_code="X", date=day, value=Decimal(amount), source="TEST"
    )


def _daily(*amounts: str) -> list[BenchmarkValue]:
    return [_value(date(2024, 1, 1 + i), amount) for i, amount in enumerate(amounts)]


# -- INDEX passes straight through -----------------------------------


def test_an_index_series_keeps_its_levels_and_its_dates():
    values = [
        _value(date(2026, 8, 17), "166784"),
        _value(date(2026, 8, 14), "166934"),
    ]

    points = to_price_points(values, IBOVESPA)

    assert [point.date for point in points] == [date(2026, 8, 14), date(2026, 8, 17)]
    assert [point.adjusted_close for point in points] == [
        Decimal(166934),
        Decimal(166784),
    ]


# -- RATE is compounded into a level ---------------------------------


def test_a_rate_series_compounds_into_an_index_from_the_base():
    """base=100, rates 1% then 2%: 101, then 101 * 1.02 = 103.02."""
    points = to_price_points(_daily("0.01", "0.02"), CDI)

    assert [point.adjusted_close for point in points] == [
        Decimal("101.00"),
        Decimal("103.0200"),
    ]


def test_the_return_between_index_points_is_the_rates_after_the_first():
    """The first observation's rate is baked into the starting level.

    Exactly as a price series behaves: a return measured from a close
    does not include the move that produced that close. Rates 1%, 2%, 3%
    give a measured return of 1.02 * 1.03 - 1 = 5.06%, not 6.1106%.
    """
    points = to_price_points(_daily("0.01", "0.02", "0.03"), CDI)

    measured = total_return(points)

    assert measured is not None
    assert measured.value == Decimal("0.0506")


def test_the_base_cancels_out_of_the_measured_return():
    rates = _daily("0.01", "0.02", "0.03")

    hundred = total_return(to_price_points(rates, CDI, base=Decimal(100)))
    one = total_return(to_price_points(rates, CDI, base=Decimal(1)))

    assert hundred is not None and one is not None
    assert hundred.value == one.value


def test_a_monthly_index_point_is_dated_at_the_end_of_the_month_it_measures():
    """The IPCA row for January is published dated 2024-01-01.

    An index level dated 2024-01-01 that already contained January's
    inflation would be a number nobody could have known on that date.
    """
    points = to_price_points([_value(date(2024, 1, 1), "0.0042")], IPCA)

    assert points[0].date == date(2024, 1, 31)


def test_a_daily_index_point_keeps_its_own_date():
    points = to_price_points([_value(date(2024, 1, 2), "0.00043739")], CDI)

    assert points[0].date == date(2024, 1, 2)


def test_deflation_lowers_the_index():
    """August 2024's IPCA was -0.02%; the level has to fall."""
    points = to_price_points(
        [_value(date(2024, 7, 1), "0.0038"), _value(date(2024, 8, 1), "-0.0002")], IPCA
    )

    assert points[1].adjusted_close < points[0].adjusted_close


def test_an_empty_series_yields_no_points():
    assert to_price_points([], CDI) == []


# -- annualised_rate -------------------------------------------------


def test_one_day_of_cdi_annualises_the_way_the_banco_central_does():
    """0.043739% a day, compounded 252 times, is the published 11.65%.

    A single observation is enough on purpose: the Banco Central
    annualises exactly one day of CDI into series 4389 and publishes it.
    """
    rate = annualised_rate([_value(date(2024, 1, 2), "0.00043739")], CDI)

    assert rate is not None
    assert round(rate * 100, 2) == Decimal("11.65")


def test_a_full_year_of_monthly_rates_annualises_to_the_year_itself():
    """Twelve monthly IPCA prints of 2024: the answer must be 4.83%.

    With n equal to the periods in a year the exponent is 1, so
    annualising cannot change the accumulated figure.
    """
    prints = [
        "0.0042",
        "0.0083",
        "0.0016",
        "0.0038",
        "0.0046",
        "0.0021",
        "0.0038",
        "-0.0002",
        "0.0044",
        "0.0056",
        "0.0039",
        "0.0052",
    ]
    values = [
        _value(date(2024, month, 1), amount)
        for month, amount in enumerate(prints, start=1)
    ]

    rate = annualised_rate(values, IPCA)

    assert rate is not None
    assert round(rate * 100, 2) == Decimal("4.83")


def test_half_a_year_of_monthly_rates_is_extrapolated_to_a_full_year():
    """Six months at 1% each annualises to 1.01 ** 12 - 1, not 1.01 ** 6 - 1."""
    values = [_value(date(2024, month, 1), "0.01") for month in range(1, 7)]

    rate = annualised_rate(values, IPCA)

    assert rate is not None
    assert round(rate, 10) == round(Decimal("1.01") ** 12 - 1, 10)


def test_annualising_and_de_annualising_leave_no_residue():
    """The round trip Sharpe depends on.

    `annualised_rate` scales by `PERIODS_PER_YEAR` and `sharpe` scales
    back by the same constant, so a constant daily rate must survive the
    trip unchanged. If the two ever used different bases — 252 here and
    365 there — every Sharpe would be wrong by a fixed factor with
    nothing in the output to show it (ADR-017, ADR-018).
    """
    daily = Decimal("0.00043739")
    values = [_value(date(2024, 1, 1 + i), str(daily)) for i in range(10)]

    annual = annualised_rate(values, CDI)

    assert annual is not None
    assert round(_periodic_rate(annual, 252), 12) == round(daily, 12)


def test_an_index_benchmark_has_no_rate_to_annualise():
    """A level's growth rate is CAGR, which is a different question."""
    assert annualised_rate([_value(date(2026, 8, 17), "166784")], IBOVESPA) is None


def test_an_empty_series_has_no_annual_rate():
    assert annualised_rate([], CDI) is None
