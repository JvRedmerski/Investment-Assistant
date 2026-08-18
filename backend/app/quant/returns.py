"""Return calculations over a price series (AGENTS.md rules 24 and 25).

A pure, deterministic, I/O-free module (rule 68 — testable with known
input and known expected output). Nothing here touches a database, a
provider or a clock: every function derives its answer solely from the
series it is given and, where relevant, an explicit `as_of` date.

## What this module does not do

It computes the return **of a price series** — an asset's return. It does
not compute the return of a *portfolio*, which is a different quantity
whenever there are contributions or withdrawals (rule 26). With cash
flows in between, `(final - initial) / initial` is patrimonial variation,
not performance, and calling it "rentabilidade" would overstate or
understate the investor's actual result. Portfolio-level return needs TWR
or MWR/IRR over the transaction ledger, and belongs to its own module.

## Input: use the adjusted close

Every function expects `PricePoint.adjusted_close`, never the raw close.
The raw close drops on an ex-dividend date and jumps on a reverse split,
so a series of raw closes reports price changes that were never losses or
gains to the holder. As of ADR-016 every stored `adjusted_close` is one
the source actually reported — none is derived from the close — but in
exchange the series may have **gaps**: the most recently closed session is
often absent for about a day, and a date whose adjustment is never
published stays absent for good.

So gaps are normal here, not exceptional. Every function below tolerates
them, and `PeriodReturn` carries the two dates it actually spans, so a
caller can tell a one-month return from one that silently covers two.

## Periodicity

`simple_return` is the primitive: a return between two prices, with no
period attached. `period_returns` groups a daily series into calendar
buckets (ISO week, month, quarter, year) and measures between the **last
available observation of consecutive buckets** — which is what makes gaps
and holidays harmless. A bucket is represented by whatever it has, not by
a fixed weekday or month-end date.

## Units

Returns are **fractions**, not percentages: `0.15` means 15%. Formatting
is a presentation concern.

## Missing data

Absent input, a series too short, a non-positive base price, or a
denominator of zero all yield `None` — never zero, never an exception,
never infinity (ADR-014). `None` means "not computable from what we
have", which is a different statement from a measured zero: a return of
`0` means the price did not move.

## `Decimal`, and why there is no `float` here

Everything stays in `Decimal`. AGENTS.md rule 17 permits `float` for
statistical work provided the decision is recorded — but this module needs
no such escape: subtraction, division and even the fractional
exponentiation CAGR requires are all `Decimal` operations, deterministic
to the active context precision (28 significant digits by default).
Converting to `float` would forfeit that for nothing.

The values are also composable — the Wave 08 benchmark comparison and the
Wave 13 backtester will chain them — so rounding at this boundary would
compound downstream. Conversion to `float` belongs where a number is
persisted or serialised, as `financial_indicators` already does.

The `float` boundary rule 17 anticipates does become necessary for
volatility, beta, Sharpe and Sortino, which need standard deviation and
covariance. That decision belongs to `risk.py`, where the need is real.

## Timezone

This module never converts a timezone and never reads a clock (rule 18).
It works on `datetime.date` values as published for the B3 session, in
whatever normalisation the ingestion layer already applied, and compares
them only to each other and to the caller's explicit `as_of`. "Today" is
never inferred — a caller wanting a trailing window must say as of when,
which is also what keeps look-ahead out (rule 108).
"""

import enum
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise

#: Calendar days per year for annualisation (ACT/365 fixed).
#:
#: Returns compound over *elapsed calendar time*, so annualising one is a
#: calendar question: an investment held from January to July grew over
#: six months of the world, regardless of how many sessions B3 held. The
#: 252-trading-day convention answers a different question — scaling a
#: per-observation statistic such as daily volatility, where what matters
#: is how many observations a year contains. That convention therefore
#: belongs to `risk.py`, and mixing the two would annualise returns and
#: volatility on incompatible clocks, corrupting any Sharpe ratio built
#: from both.
#:
#: 365 fixed rather than 365.25: over a decade the leap-day difference
#: moves an annualised return by well under a basis point, far below the
#: noise in the underlying prices, and a fixed divisor keeps the result
#: reproducible without consulting a calendar.
DAYS_PER_YEAR = Decimal(365)

#: Shortest span that may be annualised, in calendar days.
#:
#: CAGR extrapolates a holding period out to a year, so over a very short
#: span it amplifies noise into something that reads like a forecast: two
#: days of +3% annualises to roughly +25,000%. That is not a rate, it is a
#: rounding artefact wearing a percent sign. Below this floor the answer is
#: "not computable" rather than a figure nobody should act on.
#:
#: A heuristic, like `ABSURD_MOVE_THRESHOLD` in the market-data quality
#: checks — document it if tuned.
MIN_ANNUALISATION_DAYS = 30


@dataclass(frozen=True)
class PricePoint:
    """One observation of an asset's adjusted price.

    Deliberately not the full OHLCV bar: returns need one price per date,
    and narrowing the input keeps the module usable for any series —
    including the benchmark series of Wave 08, which has no OHLC at all.
    """

    date: date
    adjusted_close: Decimal


class Periodicity(str, enum.Enum):
    """The calendar bucket a series is grouped into before measuring.

    `WEEKLY` uses the **ISO** week, so the week straddling New Year stays
    one bucket instead of being split by the year boundary.
    """

    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


@dataclass(frozen=True)
class PeriodReturn:
    """A return, together with the interval it actually measured.

    The dates are not decoration. Because a series may have gaps, a
    "monthly" return can legitimately span two months, and the only way a
    caller can notice is by reading `start_date` and `end_date`.
    """

    start_date: date
    end_date: date
    start_price: Decimal
    end_price: Decimal
    value: Decimal

    @property
    def elapsed_days(self) -> int:
        return (self.end_date - self.start_date).days


def simple_return(
    start_price: Decimal | None, end_price: Decimal | None
) -> Decimal | None:
    """`(end - start) / start` — the primitive every other function uses.

    Returns `None` if either price is missing or the base price is not
    positive. A zero or negative base makes the ratio either undefined or
    sign-inverted, and neither is a return.
    """
    if start_price is None or end_price is None or start_price <= 0:
        return None
    return (end_price - start_price) / start_price


def period_returns(
    series: list[PricePoint],
    periodicity: Periodicity = Periodicity.DAILY,
    as_of: date | None = None,
) -> list[PeriodReturn]:
    """Consecutive returns over `series`, bucketed by `periodicity`.

    - **DAILY** measures between consecutive observations. Where the series
      has a gap that is a multi-day return, which `elapsed_days` reveals.
    - **WEEKLY / MONTHLY / QUARTERLY / YEARLY** keep the last observation
      of each bucket and measure between consecutive kept observations.

    `n` buckets therefore yield `n - 1` returns: the earliest observation
    is a starting point, not a return. A series with fewer than two usable
    observations yields `[]`.

    Nothing after `as_of` is read (rule 108). The result is ordered oldest
    to newest.
    """
    points = usable_series(series, as_of)
    if periodicity is not Periodicity.DAILY:
        points = _bucket_ends(points, periodicity)

    returns: list[PeriodReturn] = []
    for previous, current in pairwise(points):
        returns.append(_as_period_return(previous, current))
    return returns


def total_return(
    series: list[PricePoint], as_of: date | None = None
) -> PeriodReturn | None:
    """The return from the earliest to the latest usable observation.

    Not annualised, and not a portfolio return: for an asset held without
    cash flows this is the holding-period return; for a portfolio with
    contributions it would be patrimonial variation instead (rule 26).

    `None` when fewer than two usable observations exist.
    """
    points = usable_series(series, as_of)
    if len(points) < 2:
        return None
    return _as_period_return(points[0], points[-1])


def ytd_return(
    series: list[PricePoint], as_of: date | None = None
) -> PeriodReturn | None:
    """Year-to-date return as of `as_of` (or the latest observation).

    The base is the **last observation of the previous year**, not the
    first of the current one. Using January's first close would silently
    discard the move between the previous year's close and the new year's
    opening, which is part of this year's return.

    When the series does not reach back into the previous year — a newly
    listed asset, or simply a short window — the base falls back to the
    earliest observation within the year. That is "return since first
    observation", a narrower claim than YTD, and `start_date` is what tells
    the caller which of the two they received.

    `None` when the year holds no usable observation, or holds only the
    base.
    """
    points = usable_series(series, as_of)
    if not points:
        return None

    year = (as_of or points[-1].date).year
    within = [point for point in points if point.date.year == year]
    if not within:
        return None

    earlier = [point for point in points if point.date.year < year]
    base = earlier[-1] if earlier else within[0]
    last = within[-1]
    if base.date == last.date:
        return None
    return _as_period_return(base, last)


def cagr(series: list[PricePoint], as_of: date | None = None) -> Decimal | None:
    """Compound annual growth rate over the full usable series.

    `CAGR = (end / start) ** (365 / elapsed_calendar_days) - 1`

    The geometric mean annual rate that takes the first price to the last —
    not the arithmetic average of yearly returns, which overstates the
    outcome of a volatile series. Annualisation is on calendar days
    (`DAYS_PER_YEAR`), because compounding runs on elapsed time.

    `None` when there are fewer than two usable observations, or when they
    span less than `MIN_ANNUALISATION_DAYS`; see that constant for why a
    two-day CAGR is noise rather than a rate.
    """
    points = usable_series(series, as_of)
    if len(points) < 2:
        return None

    first, last = points[0], points[-1]
    elapsed = (last.date - first.date).days
    if elapsed < MIN_ANNUALISATION_DAYS:
        return None

    # `usable_series` guarantees both prices are positive, so the growth factor
    # is positive and its fractional power is well defined.
    growth = last.adjusted_close / first.adjusted_close
    years = Decimal(elapsed) / DAYS_PER_YEAR
    return growth ** (Decimal(1) / years) - 1


# -- series preparation, shared with `risk.py` -----------------------


def usable_series(
    series: list[PricePoint], as_of: date | None = None
) -> list[PricePoint]:
    """The series as the calculations may rely on it.

    Public because `risk.py` needs exactly these preconditions before it
    can align an asset against a benchmark: alignment has to happen after
    unusable observations are dropped, or a price discarded from one
    series alone would silently re-introduce the mismatch it is meant to
    prevent.

    Sorted oldest first, truncated at `as_of`, one observation per date,
    and free of non-positive prices.

    None of that is assumed of the input. `validate_daily_bars` already
    rejects a non-positive price and a duplicated date before storage, but
    this module is pure and reusable — a caller may pass a hand-built
    series, or a benchmark series from a source with its own quirks — so it
    establishes its own preconditions instead of trusting them. A
    non-positive price is not a price; keeping one would make every return
    touching it either undefined or sign-flipped.

    On a duplicated date the later entry in the input order wins: the sort
    is stable, so that is the caller's own last word on the date.
    """
    if as_of is not None:
        series = [point for point in series if point.date <= as_of]

    by_date: dict[date, PricePoint] = {}
    for point in sorted(series, key=lambda point: point.date):
        if point.adjusted_close > 0:
            by_date[point.date] = point
    return list(by_date.values())


# -- helpers ---------------------------------------------------------


def _bucket_ends(
    points: list[PricePoint], periodicity: Periodicity
) -> list[PricePoint]:
    """The last observation of each calendar bucket, oldest first.

    `points` must already be sorted, so the last one seen for a bucket is
    that bucket's closing observation.
    """
    ends: dict[tuple[int, ...], PricePoint] = {}
    for point in points:
        ends[_bucket_key(point.date, periodicity)] = point
    return list(ends.values())


def _bucket_key(day: date, periodicity: Periodicity) -> tuple[int, ...]:
    if periodicity is Periodicity.WEEKLY:
        iso = day.isocalendar()
        return (iso.year, iso.week)
    if periodicity is Periodicity.MONTHLY:
        return (day.year, day.month)
    if periodicity is Periodicity.QUARTERLY:
        return (day.year, (day.month - 1) // 3 + 1)
    if periodicity is Periodicity.YEARLY:
        return (day.year,)
    raise ValueError(f"Unsupported periodicity for bucketing: {periodicity}")


def _as_period_return(start: PricePoint, end: PricePoint) -> PeriodReturn:
    """Build a `PeriodReturn` from two observations known to be usable.

    `usable_series` has already guaranteed a positive base price, so the ratio is
    always defined here; `simple_return` stays the single implementation of
    the formula rather than being inlined.
    """
    value = simple_return(start.adjusted_close, end.adjusted_close)
    if value is None:  # pragma: no cover - unreachable after usable_series
        raise AssertionError("usable observations must yield a return")
    return PeriodReturn(
        start_date=start.date,
        end_date=end.date,
        start_price=start.adjusted_close,
        end_price=end.adjusted_close,
        value=value,
    )
