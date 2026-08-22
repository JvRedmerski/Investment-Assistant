"""Tests for the walk-forward partition (W14-001).

Pure dates in, pure dates out — no session, no provider, no engine. What
is exercised here is the arithmetic rule 61 and rule 62 are defined on:
three segments that tile the fold, a fold that moves, and a window too
short refused by name instead of trimmed until it fits.
"""

from datetime import date, timedelta
from itertools import pairwise

import pytest

from app.domain.backtesting.folds import (
    SEGMENT_MONTHS,
    WINDOW_TOO_SHORT,
    Partition,
    WalkForwardScheme,
    _add_months,
    partition,
)

QUARTERLY = WalkForwardScheme(segment_months=3, step_months=3)


def _test_windows(result: Partition) -> list[tuple[date, date]]:
    """Each fold's test segment, which is what must never overlap."""
    return [(fold.test.start, fold.test.end) for fold in result.folds]


# -- the shape of one fold --------------------------------------------


def test_the_default_scheme_needs_three_years_and_cuts_them_into_years():
    result = partition(date(2020, 1, 1), date(2022, 12, 31))

    assert result.required_months == 36
    assert result.available_months == 36
    assert result.refusal is None
    assert len(result.folds) == 1

    fold = result.folds[0]
    assert (fold.train.start, fold.train.end) == (date(2020, 1, 1), date(2020, 12, 31))
    assert (fold.validation.start, fold.validation.end) == (
        date(2021, 1, 1),
        date(2021, 12, 31),
    )
    assert (fold.test.start, fold.test.end) == (date(2022, 1, 1), date(2022, 12, 31))


def test_the_three_segments_tile_the_fold_with_no_gap_and_no_overlap():
    fold = partition(date(2020, 1, 1), date(2022, 12, 31), QUARTERLY).folds[0]

    assert fold.validation.start == fold.train.end + timedelta(days=1)
    assert fold.test.start == fold.validation.end + timedelta(days=1)
    assert fold.start == fold.train.start
    assert fold.end == fold.test.end


def test_every_segment_of_a_fold_is_the_same_length():
    """The confound removed by construction: same length, same portfolio age."""
    for months in (1, 3, 6, 12):
        scheme = WalkForwardScheme(segment_months=months, step_months=months)
        fold = partition(date(2020, 1, 1), date(2029, 12, 31), scheme).folds[0]

        # Calendar months hold different numbers of days, so equality is
        # asserted on month boundaries rather than on day counts.
        opening = fold.train.start
        assert fold.validation.start == _add_months(opening, months)
        assert fold.test.start == _add_months(opening, months * 2)
        assert fold.test.end == _add_months(opening, months * 3) - timedelta(days=1)


def test_test_is_always_the_latest_segment():
    """Rule 61: what chose the parameters may never be what judges them."""
    fold = partition(date(2020, 1, 1), date(2022, 12, 31)).folds[0]

    assert fold.train.end < fold.validation.start
    assert fold.validation.end < fold.test.start


# -- moving the window ------------------------------------------------


def test_a_longer_window_produces_more_folds():
    result = partition(date(2020, 1, 1), date(2023, 12, 31))

    assert [fold.index for fold in result.folds] == [0, 1]
    assert result.folds[1].train.start == date(2021, 1, 1)
    assert result.folds[1].test.end == date(2023, 12, 31)


def test_each_fold_trains_on_what_the_previous_one_validated():
    """The default step is the segment, which is the rolling scheme."""
    result = partition(date(2020, 1, 1), date(2023, 12, 31))
    first, second = result.folds

    assert (second.train.start, second.train.end) == (
        first.validation.start,
        first.validation.end,
    )


def test_test_segments_never_overlap_at_the_default_step():
    result = partition(date(2015, 1, 1), date(2024, 12, 31))

    windows = _test_windows(result)
    assert len(windows) > 1
    for earlier, later in pairwise(windows):
        assert earlier[1] < later[0]


def test_a_smaller_step_produces_more_folds_over_the_same_history():
    """More numbers out of the same evidence — allowed, and not the default."""
    rolling = partition(date(2020, 1, 1), date(2023, 12, 31))
    dense = partition(
        date(2020, 1, 1),
        date(2023, 12, 31),
        WalkForwardScheme(segment_months=12, step_months=6),
    )

    assert len(dense.folds) > len(rolling.folds)


def test_a_partial_fold_at_the_end_is_not_emitted():
    """Forty-seven months hold one three-year fold, not one and a bit."""
    result = partition(date(2020, 1, 1), date(2023, 11, 30))

    assert len(result.folds) == 1
    assert result.folds[0].test.end == date(2022, 12, 31)


# -- refusing rather than shrinking -----------------------------------


def test_a_window_too_short_is_refused_by_name_with_both_figures():
    result = partition(date(2025, 3, 19), date(2025, 12, 31))

    assert result.folds == ()
    assert result.refusal == WINDOW_TOO_SHORT
    assert result.required_months == 36
    assert result.available_months == 9


def test_the_truncated_universe_still_partitions_at_a_quarterly_scheme():
    """Nine months hold exactly one fold of three quarters — and only one."""
    result = partition(date(2025, 3, 19), date(2025, 12, 18), QUARTERLY)

    assert result.refusal is None
    assert len(result.folds) == 1
    assert result.folds[0].train.start == date(2025, 3, 19)
    assert result.folds[0].test.end == date(2025, 12, 18)


def test_an_end_before_its_start_has_no_months_and_no_folds():
    result = partition(date(2025, 6, 1), date(2025, 1, 1))

    assert result.available_months == 0
    assert result.refusal == WINDOW_TOO_SHORT


def test_a_scheme_with_a_zero_length_segment_is_rejected():
    with pytest.raises(ValueError):
        WalkForwardScheme(segment_months=0)
    with pytest.raises(ValueError):
        WalkForwardScheme(step_months=0)


# -- calendar arithmetic ----------------------------------------------


def test_a_month_end_anchor_does_not_drift_forward():
    """31 January plus one month is 28 February, never 3 March."""
    result = partition(
        date(2021, 1, 31),
        date(2021, 4, 30),
        WalkForwardScheme(segment_months=1, step_months=1),
    )

    fold = result.folds[0]
    assert fold.train.start == date(2021, 1, 31)
    assert fold.validation.start == date(2021, 2, 28)
    assert fold.test.start == date(2021, 3, 31)
    # Clamped in February and back to the 30th in April: the anchor is
    # the calendar day, not February's shortfall carried forward.
    assert fold.test.end == date(2021, 4, 29)


def test_february_of_a_leap_year_is_clamped_to_the_29th():
    fold = partition(
        date(2020, 1, 31),
        date(2020, 12, 31),
        WalkForwardScheme(segment_months=1, step_months=1),
    ).folds[0]

    assert fold.validation.start == date(2020, 2, 29)


def test_available_months_counts_inclusive_ends():
    """1 January to 31 March is three months, not two and a bit."""
    assert partition(date(2020, 1, 1), date(2020, 3, 31)).available_months == 3
    assert partition(date(2020, 1, 1), date(2020, 3, 30)).available_months == 2


# -- determinism (rule 113) -------------------------------------------


def test_the_same_window_partitions_identically_every_time():
    first = partition(date(2018, 5, 17), date(2026, 8, 22))
    second = partition(date(2018, 5, 17), date(2026, 8, 22))

    assert first == second
    assert first.scheme.segment_months == SEGMENT_MONTHS
