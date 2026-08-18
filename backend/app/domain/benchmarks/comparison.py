"""Comparing a series against a benchmark (AGENTS.md rule 28, roadmap §20).

Pure and I/O-free. It receives two `PricePoint` series — the subject and
the benchmark, both already levels, whatever they started as — and
reports the comparison. `service.py` is what loads them from the database.

Every number here comes from `app.quant`. Nothing recomputes a return or
a standard deviation, which is the point: the Wave 07 engine was written
so this wave would have nothing to calculate, only data to feed it.

## "Não comparar métricas incompatíveis sem normalização" (rule 28)

Three normalisations do that work, and each is a decision rather than a
formality:

1. **The subject is a time-weighted index, not a value.** Comparing a
   portfolio's patrimonial growth against the CDI would credit the
   investor's own deposits as performance. `portfolio.performance` is
   what strips them out.

2. **A rate benchmark is compounded into a level first**
   (`benchmarks.series`), so both sides are the same kind of quantity.

3. **Volatility is annualised**, and each side reports the periodicity it
   was measured at. An annualised figure from monthly data and one from
   daily data are both estimates of the same annual quantity; the raw
   per-period numbers would not be comparable at all.

## Beta only against an index, deliberately

`beta` is reported for an `INDEX` benchmark and left `None` for a `RATE`
one. It is not a limitation to be lifted later.

Beta measures sensitivity to a market. The CDI is not a market: it barely
varies, so `cov / var` divides by something close to zero and returns a
number that is enormous, unstable, and describes nothing. Worse, it would
not be `None` — the variance is not *exactly* zero, so the guard inside
`beta` does not fire and a meaningless figure would be reported with a
straight face. Refusing it here is the only place that can.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.benchmarks.catalog import BenchmarkDefinition
from app.integrations.benchmarks.schemas import BenchmarkKind
from app.quant.returns import (
    Periodicity,
    PricePoint,
    cagr,
    total_return,
    usable_series,
)
from app.quant.risk import beta, max_drawdown, sharpe, sortino, volatility


@dataclass(frozen=True)
class SeriesPerformance:
    """How one series behaved over the window actually measured.

    `start_date` and `end_date` are the first and last observation the
    calculation could use, not the window the caller asked for. They are
    reported because they routinely differ — a benchmark ingested later
    than the portfolio, a monthly series whose last print has not been
    published — and a comparison across two different windows is exactly
    the incompatible comparison rule 28 warns about. Made visible rather
    than silently absorbed.
    """

    start_date: date | None
    end_date: date | None
    observations: int
    periodicity: Periodicity
    total_return: Decimal | None
    annualised_return: Decimal | None
    volatility: Decimal | None
    max_drawdown: Decimal | None


@dataclass(frozen=True)
class BenchmarkComparison:
    """A subject series set against one benchmark."""

    benchmark_code: str
    benchmark_name: str
    subject: SeriesPerformance
    benchmark: SeriesPerformance
    excess_return: Decimal | None
    return_ratio: Decimal | None
    beta: Decimal | None
    sharpe: Decimal | None
    sortino: Decimal | None
    risk_free_rate: Decimal | None


def summarise(
    series: list[PricePoint],
    periodicity: Periodicity = Periodicity.DAILY,
    as_of: date | None = None,
) -> SeriesPerformance:
    """The standalone figures for one series.

    Every field is `None` when the series is too short for it, never zero
    (ADR-014) — except `max_drawdown`, where zero is a real measurement
    meaning the series never fell below a previous peak.
    """
    points = usable_series(series, as_of)
    measured = total_return(points, as_of)
    drawdown = max_drawdown(points, as_of)

    return SeriesPerformance(
        start_date=points[0].date if points else None,
        end_date=points[-1].date if points else None,
        observations=len(points),
        periodicity=periodicity,
        total_return=measured.value if measured is not None else None,
        annualised_return=cagr(points, as_of),
        volatility=volatility(points, periodicity, as_of),
        max_drawdown=drawdown.value if drawdown is not None else None,
    )


def compare(
    subject: list[PricePoint],
    benchmark_series: list[PricePoint],
    definition: BenchmarkDefinition,
    risk_free_rate: Decimal | None = None,
    periodicity: Periodicity = Periodicity.DAILY,
    as_of: date | None = None,
) -> BenchmarkComparison:
    """Set `subject` against `benchmark_series`.

    `periodicity` is the subject's own sampling; the benchmark is
    measured at the periodicity its catalog entry declares, since that is
    how often it exists.

    `risk_free_rate` is an **annual** fraction, normally the CDI over the
    same window (`benchmarks.series.annualised_rate`). It drives `sharpe`
    and `sortino`, which stay `None` without it rather than being
    computed against an assumed zero — a zero rate flatters every asset,
    and in Brazil it is not remotely close.
    """
    subject_summary = summarise(subject, periodicity, as_of)
    benchmark_summary = summarise(benchmark_series, definition.periodicity, as_of)

    return BenchmarkComparison(
        benchmark_code=definition.code,
        benchmark_name=definition.name,
        subject=subject_summary,
        benchmark=benchmark_summary,
        excess_return=_excess(
            subject_summary.total_return, benchmark_summary.total_return
        ),
        return_ratio=_ratio(
            subject_summary.total_return, benchmark_summary.total_return
        ),
        beta=(
            beta(subject, benchmark_series, periodicity, as_of)
            if definition.kind is BenchmarkKind.INDEX
            else None
        ),
        sharpe=sharpe(subject, risk_free_rate, periodicity, as_of),
        sortino=sortino(subject, risk_free_rate, periodicity, as_of),
        risk_free_rate=risk_free_rate,
    )


def _excess(subject: Decimal | None, benchmark: Decimal | None) -> Decimal | None:
    """Subject return less benchmark return, in fraction points.

    A difference, not a ratio: `0.03` means three percentage points above
    the benchmark. The two are routinely confused, and the ratio is
    reported separately as `return_ratio`.
    """
    if subject is None or benchmark is None:
        return None
    return subject - benchmark


def _ratio(subject: Decimal | None, benchmark: Decimal | None) -> Decimal | None:
    """How many times the benchmark's return the subject returned.

    `1.15` is the "115% do CDI" a Brazilian investor expects to see.

    Reported **only when both returns are strictly positive**, because
    that is the only case the idiom describes. Outside it the ratio is
    defined arithmetic that reads as the opposite of the truth, and every
    variant showed up on real data during Wave 08:

    - **Benchmark flat**: undefined, or an explosion off a denominator
      near zero. Measured against the IPCA over a quarter in which
      inflation was 0.07%, a 6% fall reported as a ratio of -85.
    - **Benchmark negative**: the ratio inverts. Falling 5% while the
      index fell 10% reads as "50% of the benchmark", which sounds like
      underperformance and is the opposite of what happened.
    - **Subject negative**: "-180% do CDI" is not a phrase that means
      anything to the reader it is written for.

    `excess_return` is defined and correct in every one of those cases,
    and is what to read there.
    """
    if subject is None or benchmark is None:
        return None
    if subject <= 0 or benchmark <= 0:
        return None
    return subject / benchmark
