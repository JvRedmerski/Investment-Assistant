"""Turning a stored benchmark series into something the quant engine reads.

`app.quant` works on `PricePoint` — a date and a level. An `INDEX`
benchmark already is that. A `RATE` benchmark is not, and this module is
the single place where the difference is resolved. Everything downstream
consumes the output of this module rather than `benchmark_values`
directly, which is what keeps a CDI rate from ever being read as if it
were a price (ADR-018).

## Why a rate becomes a level here, and not at write time

The accumulated index of a rate series depends on the date you start
accumulating from. "My portfolio against the CDI" starts at the first
contribution, which differs per portfolio and changes again whenever the
user picks a different window on screen. There is no single accumulation
to store, so the accumulation happens per query and the store keeps the
rate the source published.

## Where the index point is dated, and why it matters

The index point for a period is dated at the **end** of that period, and
it incorporates that period's rate.

For a daily series the two coincide. For the IPCA they do not: the row is
published dated 2024-01-01 but measures the whole of January. An index
level dated 2024-01-01 that already contained January's inflation would
be a number nobody could have known on that date — look-ahead by
mis-dating (AGENTS.md rule 108). Dated 2024-01-31 it is true.

## What the first point means

With `n` observations you get `n` index points, and the return between
the first and the last covers the rates of observations 2..n — the first
observation's rate is baked into the starting level, not into the
measured return.

That is the same convention a price series follows: a return measured
from a close does not include the move that produced that close. It is
what makes the two comparable, which is the entire point.

## Alignment is safe, precisely because this returns levels

A comparison intersects two series on the dates they share, and a
benchmark's calendar never matches an asset's exactly — bank holidays and
B3 holidays are different lists. Dropping a date from a *level* series
loses nothing: the level on the next shared date still carries every rate
that came before it. Dropping a date from a series of raw rates would
silently delete that day's yield. This is the concrete reason the
conversion happens before any comparison, not after.
"""

from decimal import Decimal

from app.data.models.benchmarks import BenchmarkValue
from app.domain.benchmarks.catalog import BenchmarkDefinition
from app.domain.benchmarks.data_quality import period_end_for
from app.integrations.benchmarks.schemas import BenchmarkKind
from app.quant.returns import PricePoint
from app.quant.risk import PERIODS_PER_YEAR

#: Starting level for an index accumulated from a rate series.
#:
#: Arbitrary and cancelling: every quantity derived from the series is a
#: ratio, so 100 versus 1 changes no result. 100 is chosen because it
#: makes a chart legible — a level of 114.67 reads as "up 14.67%".
DEFAULT_BASE = Decimal(100)


def to_price_points(
    values: list[BenchmarkValue],
    definition: BenchmarkDefinition,
    base: Decimal = DEFAULT_BASE,
) -> list[PricePoint]:
    """The stored series as a level series, oldest first.

    An `INDEX` passes through as published. A `RATE` is compounded into
    an index starting at `base`.

    Input order is not assumed. Returns `[]` for an empty input, which is
    "nothing ingested for this window" rather than an error — the caller
    decides whether that is worth reporting.
    """
    ordered = sorted(values, key=lambda value: value.date)

    if definition.kind is BenchmarkKind.INDEX:
        return [
            PricePoint(date=value.date, adjusted_close=value.value) for value in ordered
        ]

    points: list[PricePoint] = []
    level = base
    for value in ordered:
        level *= 1 + value.value
        points.append(
            PricePoint(
                date=period_end_for(value.date, definition.periodicity),
                adjusted_close=level,
            )
        )
    return points


def annualised_rate(
    values: list[BenchmarkValue], definition: BenchmarkDefinition
) -> Decimal | None:
    """The window's rate expressed per year, compounding.

    `(prod(1 + r)) ** (periods per year / n) - 1`

    This is what `sharpe` and `sortino` expect for `risk_free_rate`: an
    **annual** fraction, which they de-annualise back to the period with
    `(1 + annual) ** (1 / periods per year) - 1`. Annualising and
    de-annualising use the same `PERIODS_PER_YEAR`, so the round trip
    leaves no residue — 252 for a daily series, which is also the basis
    the CDI is quoted on in Brazil (ADR-018).

    A single observation is enough, unlike `cagr`, which refuses to
    annualise a window under 30 days. The difference is real rather than
    inconsistent: `cagr` extrapolates a *price move*, where two days of
    noise become a fictitious 25,000% a year. A published rate is already
    a rate — the Banco Central annualises exactly one day of CDI into
    series 4389 and publishes it.

    `None` for an `INDEX` (a level has no rate to annualise; that
    question is `cagr`) and for an empty series.
    """
    if definition.kind is not BenchmarkKind.RATE:
        return None
    if not values:
        return None

    growth = Decimal(1)
    for value in values:
        growth *= 1 + value.value
    if growth <= 0:
        # Only reachable if a -100% rate were stored, which
        # `validate_benchmark_series` rejects. Guarded anyway: a
        # fractional power of a non-positive base is undefined, and
        # "not computable" beats an exception (ADR-014).
        return None

    periods_per_year = Decimal(PERIODS_PER_YEAR[definition.periodicity])
    return growth ** (periods_per_year / Decimal(len(values))) - 1
