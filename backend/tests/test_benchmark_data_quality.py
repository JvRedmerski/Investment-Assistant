"""Tests for the benchmark data quality checks.

Pure function, known input, known output (AGENTS.md rule 68). `today` is
always passed explicitly, so every boundary of the incomplete-period rule
is reachable without touching a clock.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.benchmarks.catalog import CDI, IBOVESPA, IPCA
from app.domain.benchmarks.data_quality import (
    period_end_for,
    validate_benchmark_series,
)
from app.integrations.benchmarks.schemas import BenchmarkObservation
from app.quant.returns import Periodicity

# Far enough in the future that nothing is ever incomplete by accident.
SETTLED = date(2030, 1, 1)


def _observation(day: date, value) -> BenchmarkObservation:
    return BenchmarkObservation(
        date=day, value=None if value is None else Decimal(str(value))
    )


def _cdi(*pairs) -> list[BenchmarkObservation]:
    return [_observation(day, value) for day, value in pairs]


def test_a_clean_rate_series_passes_untouched():
    observations = _cdi(
        (date(2024, 1, 2), "0.00043739"),
        (date(2024, 1, 3), "0.00043739"),
    )

    report = validate_benchmark_series(observations, CDI, SETTLED)

    assert report.is_valid
    assert report.valid_observations == observations
    assert report.warnings == []


def test_a_missing_value_is_rejected_rather_than_stored_as_zero():
    observations = _cdi(
        (date(2024, 1, 2), "0.00043739"),
        (date(2024, 1, 3), None),
    )

    report = validate_benchmark_series(observations, CDI, SETTLED)

    assert [issue.code for issue in report.errors] == ["MISSING_VALUE"]
    assert [o.date for o in report.valid_observations] == [date(2024, 1, 2)]


def test_a_duplicated_date_drops_every_copy():
    """Neither copy can be trusted, so neither is stored.

    Same rule as `validate_daily_bars`: with two figures for one date
    there is no principled way to pick, and picking silently is worse
    than not storing.
    """
    observations = _cdi(
        (date(2024, 1, 2), "0.00043739"),
        (date(2024, 1, 2), "0.00050000"),
        (date(2024, 1, 3), "0.00043739"),
    )

    report = validate_benchmark_series(observations, CDI, SETTLED)

    assert [issue.code for issue in report.errors] == [
        "DUPLICATE_DATE",
        "DUPLICATE_DATE",
    ]
    assert [o.date for o in report.valid_observations] == [date(2024, 1, 3)]


def test_a_negative_rate_is_kept_because_deflation_is_real():
    """August 2024 IPCA was -0.02%. Rejecting it would delete history."""
    observations = [_observation(date(2024, 8, 1), "-0.0002")]

    report = validate_benchmark_series(observations, IPCA, SETTLED)

    assert report.is_valid
    assert report.valid_observations[0].value == Decimal("-0.0002")


def test_a_rate_at_or_below_minus_one_hundred_percent_is_rejected():
    """It would take an accumulated index to zero or through it."""
    observations = [_observation(date(2024, 8, 1), "-1")]

    report = validate_benchmark_series(observations, IPCA, SETTLED)

    assert [issue.code for issue in report.errors] == ["IMPOSSIBLE_RATE"]


def test_a_non_positive_index_level_is_rejected():
    observations = [_observation(date(2026, 8, 17), "0")]

    report = validate_benchmark_series(observations, IBOVESPA, SETTLED)

    assert [issue.code for issue in report.errors] == ["NON_POSITIVE_LEVEL"]


# -- the incomplete-period rule --------------------------------------


def test_a_daily_period_dated_today_is_rejected_because_the_day_is_not_over():
    observations = [_observation(date(2026, 8, 18), "166978.9375")]

    report = validate_benchmark_series(observations, IBOVESPA, date(2026, 8, 18))

    assert [issue.code for issue in report.errors] == ["INCOMPLETE_PERIOD"]


def test_a_daily_period_dated_yesterday_is_accepted():
    observations = [_observation(date(2026, 8, 17), "166784")]

    report = validate_benchmark_series(observations, IBOVESPA, date(2026, 8, 18))

    assert report.is_valid


def test_a_monthly_period_is_judged_by_its_month_end_not_its_own_date():
    """The IPCA row dated 2026-08-01 measures all of August.

    On the 18th it is not seventeen days settled — it is a third of a
    month old. A plain date comparison would have stored it.
    """
    observations = [_observation(date(2026, 8, 1), "0.005")]

    report = validate_benchmark_series(observations, IPCA, date(2026, 8, 18))

    assert [issue.code for issue in report.errors] == ["INCOMPLETE_PERIOD"]


def test_a_monthly_period_becomes_storable_once_its_month_has_ended():
    observations = [_observation(date(2026, 8, 1), "0.005")]

    report = validate_benchmark_series(observations, IPCA, date(2026, 9, 1))

    assert report.is_valid


def test_the_period_end_is_the_last_day_the_period_covers():
    assert period_end_for(date(2026, 8, 18), Periodicity.DAILY) == date(2026, 8, 18)
    # 2026-08-18 is a Tuesday; the ISO week closes on Sunday the 23rd.
    assert period_end_for(date(2026, 8, 18), Periodicity.WEEKLY) == date(2026, 8, 23)
    assert period_end_for(date(2026, 8, 18), Periodicity.MONTHLY) == date(2026, 8, 31)
    assert period_end_for(date(2026, 8, 18), Periodicity.QUARTERLY) == date(2026, 9, 30)
    assert period_end_for(date(2026, 8, 18), Periodicity.YEARLY) == date(2026, 12, 31)


def test_february_of_a_leap_year_ends_on_the_twenty_ninth():
    assert period_end_for(date(2024, 2, 1), Periodicity.MONTHLY) == date(2024, 2, 29)


def test_a_december_date_does_not_roll_into_the_next_year():
    assert period_end_for(date(2024, 12, 5), Periodicity.MONTHLY) == date(2024, 12, 31)


# -- warnings --------------------------------------------------------


def test_out_of_order_input_is_a_warning_and_nothing_is_dropped():
    observations = _cdi(
        (date(2024, 1, 3), "0.00043739"),
        (date(2024, 1, 2), "0.00043739"),
    )

    report = validate_benchmark_series(observations, CDI, SETTLED)

    assert report.is_valid
    assert [issue.code for issue in report.warnings] == ["OUT_OF_ORDER"]
    assert len(report.valid_observations) == 2


def test_an_implausible_daily_rate_is_flagged_but_still_stored():
    observations = _cdi((date(2024, 1, 2), "0.02"))

    report = validate_benchmark_series(observations, CDI, SETTLED)

    assert report.is_valid
    assert [issue.code for issue in report.warnings] == ["ABSURD_RATE"]
    assert len(report.valid_observations) == 1


def test_hyperinflation_warns_rather_than_being_erased():
    """Monthly inflation genuinely passed 80% in 1990.

    A validator that rejected it would silently truncate the series at
    the most interesting part of Brazilian monetary history.
    """
    observations = [_observation(date(1990, 3, 1), "0.8213")]

    report = validate_benchmark_series(observations, IPCA, SETTLED)

    assert report.is_valid
    assert [issue.code for issue in report.warnings] == ["ABSURD_RATE"]


def test_an_ordinary_monthly_print_does_not_trip_the_daily_bound():
    """0.83% in a month is unremarkable; the same figure in a day is not.

    This is why the bound is keyed on periodicity rather than being one
    number for every rate series.
    """
    observations = [_observation(date(2024, 2, 1), "0.0083")]

    report = validate_benchmark_series(observations, IPCA, SETTLED)

    assert report.warnings == []


def test_an_absurd_index_move_is_flagged_but_still_stored():
    observations = [
        _observation(date(2026, 8, 17), "166784"),
        _observation(date(2026, 8, 18), "60000"),
    ]

    report = validate_benchmark_series(observations, IBOVESPA, SETTLED)

    assert report.is_valid
    assert [issue.code for issue in report.warnings] == ["ABSURD_MOVE"]


def test_an_empty_series_is_valid_and_empty():
    report = validate_benchmark_series([], CDI, SETTLED)

    assert report.is_valid
    assert report.valid_observations == []
    assert report.warnings == []


@pytest.mark.parametrize("definition", [CDI, IPCA, IBOVESPA])
def test_the_rejected_count_matches_the_number_of_dropped_observations(definition):
    observations = [
        _observation(date(2024, 1, 2), None),
        _observation(date(2024, 1, 3), None),
    ]

    report = validate_benchmark_series(observations, definition, SETTLED)

    assert report.rejected_count == 2
    assert report.valid_observations == []
