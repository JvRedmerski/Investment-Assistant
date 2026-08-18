"""Unit tests for app.quant.returns (AGENTS.md rule 68: known input ->
known expected output, worked out by hand).

Prices are chosen so the expected result is exact in decimal arithmetic —
100 -> 110 is 10%, not 9.99999% — which keeps every assertion an equality
against a number computed by hand rather than an approximation.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.quant.returns import (
    DAYS_PER_YEAR,
    MIN_ANNUALISATION_DAYS,
    Periodicity,
    PricePoint,
    cagr,
    period_returns,
    simple_return,
    total_return,
    ytd_return,
)


def _point(day: date, price: str) -> PricePoint:
    return PricePoint(date=day, adjusted_close=Decimal(price))


def _series(*pairs: tuple[date, str]) -> list[PricePoint]:
    return [_point(day, price) for day, price in pairs]


# -- simple_return ---------------------------------------------------


def test_simple_return_of_a_known_gain():
    # 100 -> 110 is +10%.
    assert simple_return(Decimal(100), Decimal(110)) == Decimal("0.1")


def test_simple_return_of_a_known_loss():
    # 100 -> 75 is -25%.
    assert simple_return(Decimal(100), Decimal(75)) == Decimal("-0.25")


def test_unchanged_price_is_a_real_zero_not_none():
    # A measured zero: the price did not move. Distinct from "unknown".
    result = simple_return(Decimal(100), Decimal(100))

    assert result == Decimal(0)
    assert result is not None


@pytest.mark.parametrize(
    "start, end",
    [(None, Decimal(110)), (Decimal(100), None), (None, None)],
)
def test_missing_price_yields_none(start, end):
    assert simple_return(start, end) is None


@pytest.mark.parametrize("base", [Decimal(0), Decimal(-5)])
def test_non_positive_base_yields_none_never_an_exception(base):
    # Division by zero must not raise, and a negative base would invert
    # the sign of the result (ADR-014).
    assert simple_return(base, Decimal(110)) is None


# -- period_returns: daily -------------------------------------------


def test_daily_returns_between_consecutive_observations():
    series = _series(
        (date(2026, 1, 5), "100"),
        (date(2026, 1, 6), "110"),  # +10%
        (date(2026, 1, 7), "99"),  # -10%
    )

    results = period_returns(series, Periodicity.DAILY)

    assert [r.value for r in results] == [Decimal("0.1"), Decimal("-0.1")]
    assert [(r.start_date, r.end_date) for r in results] == [
        (date(2026, 1, 5), date(2026, 1, 6)),
        (date(2026, 1, 6), date(2026, 1, 7)),
    ]


def test_n_observations_yield_n_minus_one_returns():
    series = _series(
        (date(2026, 1, 5), "100"),
        (date(2026, 1, 6), "110"),
        (date(2026, 1, 7), "99"),
        (date(2026, 1, 8), "99"),
    )

    assert len(period_returns(series)) == 3


def test_a_gap_produces_a_multi_day_return_that_reports_its_own_span():
    """Gaps are normal (ADR-016), and must not be disguised as one day."""
    series = _series(
        (date(2026, 1, 5), "100"),
        # 2026-01-06 missing: its adjustment was never published.
        (date(2026, 1, 7), "121"),
    )

    (result,) = period_returns(series, Periodicity.DAILY)

    assert result.value == Decimal("0.21")
    assert result.elapsed_days == 2


def test_series_is_sorted_before_measuring():
    # Out-of-order input must not produce a return measured backwards.
    series = _series(
        (date(2026, 1, 7), "99"),
        (date(2026, 1, 5), "100"),
        (date(2026, 1, 6), "110"),
    )

    results = period_returns(series)

    assert [r.start_date for r in results] == [date(2026, 1, 5), date(2026, 1, 6)]
    assert [r.value for r in results] == [Decimal("0.1"), Decimal("-0.1")]


# -- period_returns: calendar buckets --------------------------------


def test_monthly_returns_measure_between_last_observations_of_each_month():
    series = _series(
        (date(2026, 1, 15), "50"),
        (date(2026, 1, 30), "100"),  # January's closing observation
        (date(2026, 2, 10), "150"),
        (date(2026, 2, 27), "120"),  # February's: +20% over January
        (date(2026, 3, 31), "60"),  # March's: -50% over February
    )

    results = period_returns(series, Periodicity.MONTHLY)

    assert [r.value for r in results] == [Decimal("0.2"), Decimal("-0.5")]
    assert [(r.start_date, r.end_date) for r in results] == [
        (date(2026, 1, 30), date(2026, 2, 27)),
        (date(2026, 2, 27), date(2026, 3, 31)),
    ]


def test_a_month_without_the_last_calendar_day_still_closes_on_what_it_has():
    # Month-end falling on a weekend or holiday must not drop the bucket.
    series = _series(
        (date(2026, 1, 29), "100"),  # January ends here for our purposes
        (date(2026, 2, 26), "125"),
    )

    (result,) = period_returns(series, Periodicity.MONTHLY)

    assert result.value == Decimal("0.25")
    assert result.start_date == date(2026, 1, 29)


def test_a_month_with_no_observation_is_skipped_and_the_span_shows_it():
    series = _series(
        (date(2026, 1, 30), "100"),
        # No February observation at all.
        (date(2026, 3, 31), "150"),
    )

    (result,) = period_returns(series, Periodicity.MONTHLY)

    assert result.value == Decimal("0.5")
    assert result.start_date == date(2026, 1, 30)
    assert result.end_date == date(2026, 3, 31)
    assert result.elapsed_days == 60


def test_quarterly_returns_group_by_calendar_quarter():
    series = _series(
        (date(2026, 3, 31), "100"),  # Q1
        (date(2026, 5, 15), "150"),
        (date(2026, 6, 30), "120"),  # Q2: +20% over Q1
        (date(2026, 9, 30), "60"),  # Q3: -50% over Q2
    )

    results = period_returns(series, Periodicity.QUARTERLY)

    assert [r.value for r in results] == [Decimal("0.2"), Decimal("-0.5")]


def test_yearly_returns_group_by_calendar_year():
    series = _series(
        (date(2024, 12, 30), "100"),
        (date(2025, 12, 29), "110"),  # +10%
        (date(2026, 12, 31), "121"),  # +10%
    )

    results = period_returns(series, Periodicity.YEARLY)

    assert [r.value for r in results] == [Decimal("0.1"), Decimal("0.1")]


def test_weekly_returns_use_the_iso_week_across_the_new_year():
    """2025-12-29 to 2026-01-04 is a single ISO week (2026-W01).

    Bucketing on `(year, week)` from `date.isocalendar()` keeps it whole;
    using the calendar year would split it and invent a return.
    """
    series = _series(
        (date(2025, 12, 26), "100"),  # ISO 2025-W52
        (date(2025, 12, 29), "150"),  # ISO 2026-W01 (Monday)
        (date(2026, 1, 2), "120"),  # ISO 2026-W01 (Friday), closes it
        (date(2026, 1, 9), "60"),  # ISO 2026-W02
    )

    results = period_returns(series, Periodicity.WEEKLY)

    assert [(r.start_date, r.end_date) for r in results] == [
        (date(2025, 12, 26), date(2026, 1, 2)),
        (date(2026, 1, 2), date(2026, 1, 9)),
    ]
    assert [r.value for r in results] == [Decimal("0.2"), Decimal("-0.5")]


# -- look-ahead ------------------------------------------------------


def test_as_of_excludes_later_observations():
    """No window may read a price published after its reference date."""
    series = _series(
        (date(2026, 1, 5), "100"),
        (date(2026, 1, 6), "110"),
        (date(2026, 1, 7), "500"),  # must not be visible as of the 6th
    )

    results = period_returns(series, Periodicity.DAILY, as_of=date(2026, 1, 6))

    assert [r.value for r in results] == [Decimal("0.1")]


def test_as_of_on_a_date_without_an_observation_still_truncates():
    series = _series(
        (date(2026, 1, 5), "100"),
        (date(2026, 1, 6), "110"),
        (date(2026, 1, 9), "500"),
    )

    result = total_return(series, as_of=date(2026, 1, 7))

    assert result is not None
    assert result.end_date == date(2026, 1, 6)
    assert result.value == Decimal("0.1")


# -- edge cases: empty, single point, duplicates ---------------------


@pytest.mark.parametrize("periodicity", list(Periodicity))
def test_empty_series_yields_no_returns_for_any_periodicity(periodicity):
    assert period_returns([], periodicity) == []


@pytest.mark.parametrize("periodicity", list(Periodicity))
def test_single_observation_yields_no_returns(periodicity):
    # One price is a starting point, not a return.
    assert period_returns(_series((date(2026, 1, 5), "100")), periodicity) == []


def test_empty_and_single_point_series_have_no_total_return_or_cagr():
    single = _series((date(2026, 1, 5), "100"))

    assert total_return([]) is None
    assert total_return(single) is None
    assert cagr([]) is None
    assert cagr(single) is None
    assert ytd_return([]) is None


def test_non_positive_prices_are_discarded_from_the_series():
    series = _series(
        (date(2026, 1, 5), "100"),
        (date(2026, 1, 6), "0"),  # not a price
        (date(2026, 1, 7), "110"),
    )

    (result,) = period_returns(series, Periodicity.DAILY)

    assert result.value == Decimal("0.1")
    assert (result.start_date, result.end_date) == (date(2026, 1, 5), date(2026, 1, 7))


def test_a_duplicated_date_keeps_the_last_entry_given():
    series = _series(
        (date(2026, 1, 5), "100"),
        (date(2026, 1, 6), "999"),
        (date(2026, 1, 6), "110"),  # caller's last word on the 6th
    )

    (result,) = period_returns(series, Periodicity.DAILY)

    assert result.value == Decimal("0.1")


# -- total_return ----------------------------------------------------


def test_total_return_spans_the_whole_series_ignoring_the_path():
    series = _series(
        (date(2026, 1, 5), "100"),
        (date(2026, 3, 2), "20"),  # a crash in between is irrelevant
        (date(2026, 6, 30), "175"),
    )

    result = total_return(series)

    assert result is not None
    assert result.value == Decimal("0.75")
    assert (result.start_date, result.end_date) == (date(2026, 1, 5), date(2026, 6, 30))
    assert result.start_price == Decimal(100)
    assert result.end_price == Decimal(175)


# -- ytd_return ------------------------------------------------------


def test_ytd_is_measured_from_the_last_close_of_the_previous_year():
    """The base is December's close, not January's first observation.

    Anchoring on January's first close would drop the move from the
    previous year's close into the new year's opening, which belongs to
    this year's return.
    """
    series = _series(
        (date(2025, 12, 30), "100"),  # the correct base
        (date(2026, 1, 2), "105"),  # anchoring here would understate
        (date(2026, 4, 30), "130"),
    )

    result = ytd_return(series, as_of=date(2026, 4, 30))

    assert result is not None
    assert result.start_date == date(2025, 12, 30)
    assert result.value == Decimal("0.3")


def test_ytd_falls_back_to_the_first_observation_of_the_year_when_no_prior_year():
    # A newly listed asset: "since first observation", and start_date is
    # what tells the caller that is what they got.
    series = _series(
        (date(2026, 1, 2), "100"),
        (date(2026, 4, 30), "130"),
    )

    result = ytd_return(series, as_of=date(2026, 4, 30))

    assert result is not None
    assert result.start_date == date(2026, 1, 2)
    assert result.value == Decimal("0.3")


def test_ytd_ignores_observations_after_as_of():
    series = _series(
        (date(2025, 12, 30), "100"),
        (date(2026, 4, 30), "130"),
        (date(2026, 7, 31), "500"),
    )

    result = ytd_return(series, as_of=date(2026, 4, 30))

    assert result is not None
    assert result.value == Decimal("0.3")


def test_ytd_defaults_to_the_latest_observation_when_no_as_of_is_given():
    series = _series(
        (date(2025, 12, 30), "100"),
        (date(2026, 4, 30), "130"),
    )

    result = ytd_return(series)

    assert result is not None
    assert result.end_date == date(2026, 4, 30)
    assert result.value == Decimal("0.3")


def test_ytd_is_none_when_the_year_holds_only_the_base():
    # Nothing has been observed in the requested year yet.
    series = _series((date(2025, 12, 30), "100"))

    assert ytd_return(series, as_of=date(2026, 4, 30)) is None


def test_ytd_is_none_when_the_year_has_a_single_observation_and_no_prior_year():
    series = _series((date(2026, 1, 2), "100"))

    assert ytd_return(series, as_of=date(2026, 4, 30)) is None


# -- cagr ------------------------------------------------------------


def test_cagr_of_a_doubling_over_two_years():
    """730 days is exactly 2 years at ACT/365, so CAGR = sqrt(2) - 1.

    Worked by hand: (200/100) ** (365/730) - 1 = 2 ** 0.5 - 1
    = 0.41421356237309504880168872... (~41.42% a year).
    """
    series = _series(
        (date(2025, 1, 1), "100"),
        (date(2027, 1, 1), "200"),  # 365 + 365 = 730 days, no leap year
    )

    result = cagr(series)

    assert result is not None
    assert (series[1].date - series[0].date).days == 730
    assert result == Decimal(2) ** (Decimal(1) / Decimal(2)) - 1
    # Compounding it back over the two years returns the growth factor.
    assert (1 + result) ** 2 == pytest.approx(Decimal(2), abs=Decimal("1e-25"))


def test_cagr_over_exactly_one_year_equals_the_simple_return():
    # Over a single year there is nothing to compound, so the annual rate
    # is just the period return: 100 -> 110 is 10%.
    series = _series(
        (date(2025, 1, 1), "100"),
        (date(2026, 1, 1), "110"),  # 2025 is not a leap year: 365 days
    )

    result = cagr(series)

    assert result is not None
    assert (series[1].date - series[0].date).days == int(DAYS_PER_YEAR)
    assert result == pytest.approx(Decimal("0.1"), abs=Decimal("1e-25"))


def test_cagr_of_a_loss_is_negative():
    # Halving over two years: 0.5 ** 0.5 - 1 = -0.2928932188...
    series = _series(
        (date(2025, 1, 1), "100"),
        (date(2027, 1, 1), "50"),  # 730 days
    )

    result = cagr(series)

    assert result is not None
    assert result == Decimal("0.5") ** (Decimal(1) / Decimal(2)) - 1
    assert result < 0


def test_cagr_uses_only_the_endpoints_not_the_path():
    with_path = _series(
        (date(2025, 1, 1), "100"),
        (date(2026, 6, 1), "10"),
        (date(2027, 1, 1), "200"),
    )
    endpoints_only = _series(
        (date(2025, 1, 1), "100"),
        (date(2027, 1, 1), "200"),
    )

    assert cagr(with_path) == cagr(endpoints_only)


def test_cagr_is_none_for_a_span_too_short_to_annualise():
    """A few days of noise must not be extrapolated into a yearly rate."""
    series = _series(
        (date(2026, 1, 5), "100"),
        (date(2026, 1, 7), "103"),  # 2 days, +3%
    )

    assert (series[1].date - series[0].date).days < MIN_ANNUALISATION_DAYS
    assert cagr(series) is None


def test_cagr_is_computed_right_at_the_annualisation_floor():
    series = _series(
        (date(2026, 1, 1), "100"),
        (date(2026, 1, 31), "110"),  # exactly 30 days
    )

    assert (series[1].date - series[0].date).days == MIN_ANNUALISATION_DAYS
    assert cagr(series) is not None


def test_cagr_respects_as_of_including_the_short_span_guard():
    series = _series(
        (date(2026, 1, 5), "100"),
        (date(2026, 1, 7), "103"),
        (date(2027, 1, 5), "200"),  # invisible as of 2026-01-07
    )

    assert cagr(series, as_of=date(2026, 1, 7)) is None
    assert cagr(series) is not None
