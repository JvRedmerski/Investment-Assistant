"""Cutting a window into train / validation / test, and moving it forward.

Pure, deterministic and I/O-free (rule 68): dates in, dates out. Nothing
here knows what a backtest is — it only decides which periods one may be
measured over, and refuses to invent periods the data cannot hold.

Rule 61 asks for `Training / Validation / Test` and forbids calibrating
and validating on the same history. Rule 62 asks for the window to then
**move**: `Train → Validate → Test → Move window → Repeat`. This module
is that partition and nothing else; who runs what over each segment is
`walkforward`.

## The three segments are the same length, and that is the load-bearing bit

It reads like an arbitrary simplification and it is the opposite. The
strategy under test builds a portfolio out of monthly contributions, so
**how long a segment is changes what it measures**: a three-month run
holds three contributions into a portfolio that was empty in January, and
a twelve-month run holds twelve into one that already has weights,
sectors, and a Diversification pillar reading them back.

Segments of different lengths therefore produce figures that are not
comparable — and the whole point of the wave is a comparison, between
what was chosen in-sample and what happened out-of-sample. A shorter test
segment would report a degradation that is partly just a younger
portfolio, and nobody could say which part.

So the confound is removed by construction rather than corrected for
afterwards, the same way `allocation` refuses to rank two scores with
different coverage instead of adjusting one to the other.

## A fold that does not fit is refused by name, never shrunk to fit

Three segments of `segment_months` need `3 × segment_months` of window.
When the history is shorter, the honest answer is `WINDOW_TOO_SHORT` with
both figures — not segments quietly trimmed until they fit, which would
produce a validated-looking result out of a window that validated
nothing.

This is not hypothetical here. The universe of four tracked assets has
its total-return series truncated to nine months by ADR-032, so the
default scheme refuses on the real database and says by how much.

## Where the window comes from, and why folds overlap

`window_start` is the first session every asset in the universe is
measurable from, which ADR-032 already decides — this module receives it.
Folds then start every `step_months`, so with the default step each
fold's train segment is the previous fold's validation segment, and the
**test** segments tile the history end to end without overlapping each
other. That is what makes one out-of-sample figure per fold add up to a
statement about the strategy, rather than the same period counted twice.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

#: Length of each of the three segments, in months.
#:
#: A year each — three years per fold. Round and coarse on purpose
#: (rule 60): a strategy that contributes monthly needs a segment long
#: enough for the portfolio to stop being a first purchase, and twelve
#: months is the shortest span that covers a full cycle of the annual
#: statements the score reads.
SEGMENT_MONTHS = 12

#: How far the whole fold slides between repetitions, in months.
#:
#: Equal to the segment by default, which is the textbook rolling
#: walk-forward: each fold's train segment is the previous fold's
#: validation segment, and the test segments tile the history without
#: overlapping. A smaller step produces more folds out of the same
#: history and they share test data — more numbers, not more evidence.
STEP_MONTHS = SEGMENT_MONTHS

#: The window cannot hold one whole fold of three segments.
WINDOW_TOO_SHORT = "WINDOW_TOO_SHORT"


@dataclass(frozen=True)
class WalkForwardScheme:
    """How the history is to be cut, and how far the cut travels."""

    segment_months: int = SEGMENT_MONTHS
    step_months: int = STEP_MONTHS

    def __post_init__(self) -> None:
        if self.segment_months < 1:
            raise ValueError("segment_months must be at least 1")
        if self.step_months < 1:
            raise ValueError("step_months must be at least 1")

    @property
    def fold_months(self) -> int:
        """Months one fold needs: train, validation and test together."""
        return self.segment_months * 3


@dataclass(frozen=True)
class Segment:
    """One period a strategy may be measured over, both ends inclusive."""

    start: date
    end: date


@dataclass(frozen=True)
class Fold:
    """One repetition of `Train → Validate → Test`.

    The three roles are not interchangeable, and the order they are named
    in is chronological on purpose: **test is always the latest**, so a
    choice made on the first two segments is judged on history neither of
    them saw (rule 61).
    """

    index: int
    train: Segment
    validation: Segment
    test: Segment

    @property
    def start(self) -> date:
        return self.train.start

    @property
    def end(self) -> date:
        return self.test.end


@dataclass(frozen=True)
class Partition:
    """The folds a window supports, or the named reason it supports none.

    `available_months` and `required_months` travel with the refusal
    because *"why did my walk-forward return nothing?"* has to be
    answerable from the result — the same reason `BacktestWindow` carries
    `bounded_by`.
    """

    scheme: WalkForwardScheme
    window_start: date
    window_end: date
    folds: tuple[Fold, ...]
    required_months: int
    available_months: int
    refusal: str | None = None


def partition(
    window_start: date,
    window_end: date,
    scheme: WalkForwardScheme = WalkForwardScheme(),
) -> Partition:
    """Cut `[window_start, window_end]` into as many folds as it holds.

    Folds are emitted while a whole one fits — a partial fold is not a
    shorter fold, it is a fold missing one of the three segments the
    method is defined on.
    """
    folds: list[Fold] = []
    index = 0
    while True:
        opening = _add_months(window_start, index * scheme.step_months)
        segments = _segments(opening, scheme.segment_months)
        if segments[-1].end > window_end:
            break
        folds.append(
            Fold(
                index=index,
                train=segments[0],
                validation=segments[1],
                test=segments[2],
            )
        )
        index += 1

    return Partition(
        scheme=scheme,
        window_start=window_start,
        window_end=window_end,
        folds=tuple(folds),
        required_months=scheme.fold_months,
        available_months=_months_between(window_start, window_end),
        refusal=WINDOW_TOO_SHORT if not folds else None,
    )


# -- month arithmetic -------------------------------------------------


def _segments(opening: date, segment_months: int) -> tuple[Segment, ...]:
    """Three consecutive segments of equal length, from `opening`.

    Each ends the day before the next begins, so the three tile the fold
    with no gap and no overlap: a session belongs to exactly one of
    train, validation and test, which is what rule 61 is asking for.
    """
    bounds = [_add_months(opening, segment_months * step) for step in range(4)]
    return tuple(
        Segment(start=bounds[index], end=bounds[index + 1] - timedelta(days=1))
        for index in range(3)
    )


def _add_months(day: date, months: int) -> date:
    """`day` moved `months` forward, clamped to the end of short months.

    31 January plus one month is 28 February, not 3 March. Clamping is
    what keeps a partition anchored to the calendar it started on: a
    scheme opening on a 31st must not drift a few days later every time
    the window moves.
    """
    if months == 0:
        return day
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _months_between(start: date, end: date) -> int:
    """Whole months from `start` to the day after `end`.

    The day after, because both ends of a window are inclusive: 1 January
    to 31 March is three months, not two and a bit. Never negative — an
    end before its start has no months, which the caller reports as a
    refusal rather than as a negative quantity.
    """
    boundary = end + timedelta(days=1)
    months = (boundary.year - start.year) * 12 + (boundary.month - start.month)
    if boundary.day < start.day:
        months -= 1
    return max(months, 0)
