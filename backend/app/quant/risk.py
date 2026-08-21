"""Risk metrics over a price series (AGENTS.md rules 24 and 27).

Pure, deterministic, I/O-free, like `returns.py`, and built on it: the
periodic return series every metric here needs comes from
`period_returns`, never from a second implementation of the return
formula.

Each metric below carries its definition, formula, periodicity and
missing-data behaviour, as rule 27 requires.

## Annualisation: 252 sessions, and why it is not 365

`returns.py` annualises on **calendar days** (`DAYS_PER_YEAR = 365`)
because compound return accrues over elapsed time — a holiday does not
suspend interest. Dispersion is a different quantity: standard deviation
is measured **per observation**, and annualising it means scaling by
`sqrt(observations per year)`. A year holds about 252 B3 sessions, not
365 of them.

`PERIODS_PER_YEAR` is therefore defined here rather than imported from
`returns.py`, deliberately (ADR-017). Annualising dispersion on 365 would
inflate it by `sqrt(365 / 252)`, about 19%, and since Sharpe divides an
annualised return by an annualised volatility, the ratio would come out
wrong by that same constant factor with nothing in the output to reveal
it. If a Sharpe figure ever looks off by roughly 1.2, this is the first
place to look.

Sharpe and Sortino avoid the question entirely by construction: they scale
numerator and denominator with the **same** factor (see `sharpe`), so the
ratio is dimensionally consistent whatever that factor is.

## `Decimal`, and the `float` boundary that never materialised

ADR-017 left open where `Decimal` should give way to `float`, expecting
this module to need it — rule 17 permits `float` for statistical work
provided the decision is recorded, and `numpy`/`scipy` have sat in
`pyproject.toml` unused since Wave 00.

Examined against the actual requirement, the boundary is not needed here
either. Every operation these metrics use is available in `Decimal` and
deterministic to the context precision: standard deviation and covariance
are sums, products and divisions; annualisation needs `Decimal.sqrt()`;
de-annualising a rate needs a fractional power. Nothing calls for a
matrix library or a transcendental function.

So the quant engine stays entirely in `Decimal`, and `numpy` remains
unimported. Determinism is the reason to prefer it where it costs nothing
(rule 113): a `float` sum depends on summation order, while `Decimal` at
28 significant digits does not drift over a series of a few thousand
observations. See the dated addendum in ADR-017.

## Asset risk, not portfolio risk

Every function here measures **one asset's** series. Portfolio volatility
is not the average of its holdings' volatilities — it needs the covariance
matrix between them and the position weights, which cancel risk to the
extent the assets are uncorrelated. Computing it needs weights, which come
from the position engine, so it belongs with portfolio analytics rather
than here. Recorded as Future Work; do not approximate it by averaging.

## Missing data

Absent input, a series too short to estimate from, and a zero denominator
all yield `None` — never zero, never an exception (ADR-014). The
distinction matters especially for `max_drawdown`, where `0` is a real
measurement (the series never fell below a previous peak) and `None` means
there was not enough data to look.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.quant.returns import (
    Periodicity,
    PricePoint,
    cagr,
    period_returns,
    usable_series,
)

#: Observations per year, by periodicity, for annualising dispersion.
#:
#: 252 is the conventional count of B3 trading sessions in a year (365
#: calendar days less weekends and roughly 10 holidays). Defined here and
#: NOT imported from `returns.py`, whose 365 answers a different question
#: — see the module docstring and ADR-017.
#:
#: The weekly, monthly and quarterly figures are exact by construction: a
#: year has 52 ISO weeks (barring the 53-week years, whose effect on a
#: square root is negligible), 12 months and 4 quarters.
PERIODS_PER_YEAR: dict[Periodicity, int] = {
    Periodicity.DAILY: 252,
    Periodicity.WEEKLY: 52,
    Periodicity.MONTHLY: 12,
    Periodicity.QUARTERLY: 4,
    Periodicity.YEARLY: 1,
}

#: Fewest return observations any estimate is made from.
#:
#: Sample standard deviation divides by `n - 1`, so two observations are
#: the arithmetic minimum. This is a floor on what is *defined*, not on
#: what is *meaningful*: a volatility estimated from two returns is
#: dominated by noise. Callers presenting these numbers should apply their
#: own, larger window.
MIN_OBSERVATIONS = 2


@dataclass(frozen=True)
class Drawdown:
    """The worst peak-to-trough decline found in a series.

    Carries the dates and prices so a caller can say *when* the loss
    happened, not merely how deep it was — a 30% drawdown recovered in a
    month and one still open two years later are different facts.
    """

    peak_date: date
    peak_price: Decimal
    trough_date: date
    trough_price: Decimal
    value: Decimal


def standard_deviation(values: list[Decimal]) -> Decimal | None:
    """Sample standard deviation of `values`.

    `sqrt( sum((x - mean)^2) / (n - 1) )`

    The sample form (`n - 1`, Bessel's correction), not the population
    form: a price history is a sample of the process that generated it,
    not the whole population, and dividing by `n` would bias the estimate
    low. Periodicity is whatever the caller's `values` carry — this
    function does not annualise.

    `None` when fewer than `MIN_OBSERVATIONS` values are given.
    """
    if len(values) < MIN_OBSERVATIONS:
        return None
    mean = sum(values, Decimal(0)) / len(values)
    variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / (
        len(values) - 1
    )
    return variance.sqrt()


def downside_deviation(
    values: list[Decimal], target: Decimal = Decimal(0)
) -> Decimal | None:
    """Dispersion of the shortfalls below `target` only.

    `sqrt( sum(min(x - target, 0)^2) / (n - 1) )`

    The denominator counts **all** observations, not just the ones that
    fell short. That is the original Sortino formulation, and it keeps the
    result comparable with `standard_deviation` over the same sample:
    dividing by the count of shortfalls instead would report a *larger*
    downside risk for an asset whose losses are rarer, which inverts the
    meaning.

    `None` when fewer than `MIN_OBSERVATIONS` values are given, or when
    nothing fell below `target`. The second case is not zero risk — it is
    a sample that contains no evidence about downside, and reporting `0`
    would make the Sortino ratio divide by zero or, worse, look infinitely
    good.
    """
    if len(values) < MIN_OBSERVATIONS:
        return None
    shortfalls = [value - target for value in values if value < target]
    if not shortfalls:
        return None
    total = sum((shortfall**2 for shortfall in shortfalls), Decimal(0))
    return (total / (len(values) - 1)).sqrt()


def volatility(
    series: list[PricePoint],
    periodicity: Periodicity = Periodicity.DAILY,
    as_of: date | None = None,
    annualised: bool = True,
) -> Decimal | None:
    """Standard deviation of `periodicity` returns, annualised by default.

    `vol = stdev(periodic returns) * sqrt(PERIODS_PER_YEAR[periodicity])`

    Expressed as a fraction: `0.25` is 25% a year. Set `annualised=False`
    for the raw per-period figure.

    Nothing after `as_of` is read (rule 108). `None` when there are fewer
    than `MIN_OBSERVATIONS` returns available.
    """
    returns = _periodic_return_values(series, periodicity, as_of)
    deviation = standard_deviation(returns)
    if deviation is None:
        return None
    if not annualised:
        return deviation
    return deviation * Decimal(PERIODS_PER_YEAR[periodicity]).sqrt()


def max_drawdown(
    series: list[PricePoint], as_of: date | None = None
) -> Drawdown | None:
    """The deepest peak-to-trough decline in the series.

    `max_drawdown = min over t of ( P_t / max(P_s for s <= t) - 1 )`

    Measured on prices rather than returns, and reported as a **negative**
    fraction: `-0.35` means the series fell 35% below its running peak.
    Signed, so it composes with returns without a sign convention to
    remember.

    The peak is a *running* maximum, so only prior prices are ever
    consulted — the metric is free of look-ahead by construction, over and
    above the `as_of` truncation.

    A series that only ever rises yields `0`, which is a real measurement,
    not a missing one. Recovery is not reported: `Drawdown` answers how
    deep and when, and pairing it with a recovery date would need a
    convention for a drawdown still open at `as_of`.

    `None` when fewer than two usable observations exist.
    """
    points = usable_series(series, as_of)
    if len(points) < 2:
        return None

    peak = points[0]
    worst: Drawdown | None = None
    for point in points[1:]:
        if point.adjusted_close > peak.adjusted_close:
            peak = point
            continue
        decline = point.adjusted_close / peak.adjusted_close - 1
        if worst is None or decline < worst.value:
            worst = Drawdown(
                peak_date=peak.date,
                peak_price=peak.adjusted_close,
                trough_date=point.date,
                trough_price=point.adjusted_close,
                value=decline,
            )

    if worst is None:
        # Monotonically rising: no price ever sat below a prior peak.
        return Drawdown(
            peak_date=points[0].date,
            peak_price=points[0].adjusted_close,
            trough_date=points[0].date,
            trough_price=points[0].adjusted_close,
            value=Decimal(0),
        )
    return worst


def beta(
    series: list[PricePoint],
    benchmark: list[PricePoint] | None = None,
    periodicity: Periodicity = Periodicity.DAILY,
    as_of: date | None = None,
) -> Decimal | None:
    """Sensitivity of the asset's returns to the benchmark's.

    `beta = cov(asset returns, benchmark returns) / var(benchmark returns)`

    Dimensionless, so it is never annualised. `1` means the asset moved
    with the benchmark, `0.5` half as much, a negative value inversely.

    Both covariance and variance use the sample form (`n - 1`), which
    cancels in the ratio but is stated because the two must match.

    **The two series are aligned on the dates they share, before returns
    are computed.** This is the reason `beta` takes prices rather than two
    ready-made return series: gaps are normal (ADR-016), and a return
    spanning 08-16 to 08-18 because the asset is missing 08-17 is not
    comparable with the benchmark's 08-17 to 08-18. Pairing them by
    position would quietly regress one interval on a different one.

    `benchmark` is `None` until the Wave 08 benchmark series exists, and
    the answer is `None` with it — the parameter is here so the shape of
    the call is settled without anticipating that wave.

    `None` also when fewer than `MIN_OBSERVATIONS` aligned returns remain,
    or when the benchmark did not move at all (zero variance leaves the
    sensitivity undefined rather than infinite).
    """
    if not benchmark:
        return None

    asset_returns, benchmark_returns = _aligned_return_values(
        series, benchmark, periodicity, as_of
    )
    if len(benchmark_returns) < MIN_OBSERVATIONS:
        return None

    benchmark_mean = sum(benchmark_returns, Decimal(0)) / len(benchmark_returns)
    asset_mean = sum(asset_returns, Decimal(0)) / len(asset_returns)

    covariance = sum(
        (
            (asset - asset_mean) * (mark - benchmark_mean)
            for asset, mark in zip(asset_returns, benchmark_returns)
        ),
        Decimal(0),
    )
    variance = sum(
        ((mark - benchmark_mean) ** 2 for mark in benchmark_returns), Decimal(0)
    )
    if variance == 0:
        return None
    return covariance / variance


def alpha(
    series: list[PricePoint],
    benchmark: list[PricePoint] | None = None,
    risk_free_rate: Decimal | None = None,
    periodicity: Periodicity = Periodicity.DAILY,
    as_of: date | None = None,
) -> Decimal | None:
    """Return earned beyond what the market exposure alone would explain.

    `alpha = R - [ Rf + beta * (Rm - Rf) ]`

    Jensen's alpha, as an **annual** fraction: `R` and `Rm` are the
    subject's and the benchmark's CAGR, `Rf` the annual risk-free rate,
    and `beta` the sensitivity measured by `beta` above.

    ## Not the same figure as excess return, and the difference is the point

    `benchmarks.comparison.excess_return` is a plain difference: it says
    the subject beat the index by so many points and asks nothing about
    how. A portfolio of high-beta assets beats a rising index almost by
    construction, and that is not skill — it is leverage on the same
    market move. Alpha charges the subject for exactly the return its
    beta already entitled it to, and reports what is left.

    The corollary matters for reading a backtest: a *positive* excess
    return with a *negative* alpha means the strategy went up because the
    market did, and by less than its risk exposure should have delivered.

    Both series are measured over whatever window they are given, so the
    caller must hand over two series already cut to the period they
    share — `compare` aligns them before calling. Passing mismatched
    windows compares two different periods, which rule 28 forbids.

    `None` when beta cannot be estimated, when either series is too short
    to annualise (see `cagr`), or when the risk-free rate is absent. Never
    zero for any of those: a missing alpha is not a zero alpha (ADR-014).
    """
    if risk_free_rate is None:
        return None

    sensitivity = beta(series, benchmark, periodicity, as_of)
    if sensitivity is None:
        return None

    subject_return = cagr(series, as_of)
    benchmark_return = cagr(benchmark or [], as_of)
    if subject_return is None or benchmark_return is None:
        return None

    expected = risk_free_rate + sensitivity * (benchmark_return - risk_free_rate)
    return subject_return - expected


def sharpe(
    series: list[PricePoint],
    risk_free_rate: Decimal | None = None,
    periodicity: Periodicity = Periodicity.DAILY,
    as_of: date | None = None,
) -> Decimal | None:
    """Excess return per unit of total volatility, annualised.

    `sharpe = mean(excess) / stdev(excess) * sqrt(periods per year)`

    where `excess` is each periodic return less the risk-free rate for
    that same period.

    Numerator and denominator are scaled by the **same** `sqrt(periods per
    year)` factor, which is what makes the ratio consistent regardless of
    periodicity — and what keeps the calendar-versus-session question of
    ADR-017 out of it. Note the mean is arithmetic here, not the geometric
    CAGR of `returns.py`: pairing an arithmetic mean with the standard
    deviation of the same observations is what the ratio is defined on.

    `risk_free_rate` is an **annual** fraction (CDI is quoted that way:
    `Decimal("0.1075")` for 10.75% a year), de-annualised geometrically to
    the period — see `_periodic_rate`. It is `None` until the Wave 08 CDI
    series exists, and the answer is `None` with it.

    Since a constant rate shifts every observation equally,
    `stdev(excess) == stdev(returns)`; excess returns are used anyway so
    the formula reads as defined.

    `None` when the rate is absent, when fewer than `MIN_OBSERVATIONS`
    returns are available, or when volatility is zero (no dispersion
    leaves risk-adjusted return undefined, not infinite).
    """
    excess = _excess_returns(series, risk_free_rate, periodicity, as_of)
    if excess is None:
        return None

    deviation = standard_deviation(excess)
    if deviation is None or deviation == 0:
        return None

    mean = sum(excess, Decimal(0)) / len(excess)
    return mean / deviation * Decimal(PERIODS_PER_YEAR[periodicity]).sqrt()


def sortino(
    series: list[PricePoint],
    risk_free_rate: Decimal | None = None,
    periodicity: Periodicity = Periodicity.DAILY,
    as_of: date | None = None,
) -> Decimal | None:
    """Excess return per unit of *downside* volatility, annualised.

    `sortino = mean(excess) / downside_deviation(excess, 0)
               * sqrt(periods per year)`

    Identical to `sharpe` except that the denominator counts only the
    periods that fell short of the risk-free rate. The rationale is that
    upside dispersion is not a risk the investor wants penalised: an asset
    that rises in violent jumps is punished by Sharpe and left alone by
    Sortino.

    The shortfall target is the risk-free rate itself, so it is zero in
    excess-return terms.

    `None` under the same conditions as `sharpe`, plus when no period fell
    below the target — a sample with no downside carries no evidence about
    downside risk, and reporting zero there would make the ratio look
    infinitely good (see `downside_deviation`).
    """
    excess = _excess_returns(series, risk_free_rate, periodicity, as_of)
    if excess is None:
        return None

    deviation = downside_deviation(excess, Decimal(0))
    if deviation is None or deviation == 0:
        return None

    mean = sum(excess, Decimal(0)) / len(excess)
    return mean / deviation * Decimal(PERIODS_PER_YEAR[periodicity]).sqrt()


# -- helpers ---------------------------------------------------------


def _periodic_return_values(
    series: list[PricePoint],
    periodicity: Periodicity,
    as_of: date | None,
) -> list[Decimal]:
    """The return values only, in chronological order.

    Delegates to `period_returns` so the return formula, the `as_of`
    truncation and the calendar bucketing have exactly one implementation.
    """
    return [result.value for result in period_returns(series, periodicity, as_of=as_of)]


def _periodic_rate(annual_rate: Decimal, periods_per_year: int) -> Decimal:
    """An annual rate expressed per period, compounding.

    `(1 + annual) ** (1 / periods per year) - 1`

    Geometric, not `annual / periods_per_year`: the simple division would
    ignore compounding and overstate the periodic rate, which then
    understates every excess return measured against it.
    """
    return (1 + annual_rate) ** (Decimal(1) / Decimal(periods_per_year)) - 1


def _excess_returns(
    series: list[PricePoint],
    risk_free_rate: Decimal | None,
    periodicity: Periodicity,
    as_of: date | None,
) -> list[Decimal] | None:
    """Periodic returns less the periodic risk-free rate.

    `None` when the rate is unavailable — the Wave 08 dependency — so
    callers get "not computable" rather than a ratio silently computed
    against a zero rate, which would flatter every asset.
    """
    if risk_free_rate is None:
        return None
    returns = _periodic_return_values(series, periodicity, as_of)
    if len(returns) < MIN_OBSERVATIONS:
        return None
    periodic_rate = _periodic_rate(risk_free_rate, PERIODS_PER_YEAR[periodicity])
    return [value - periodic_rate for value in returns]


def _aligned_return_values(
    series: list[PricePoint],
    benchmark: list[PricePoint],
    periodicity: Periodicity,
    as_of: date | None,
) -> tuple[list[Decimal], list[Decimal]]:
    """Return series measured over identical intervals.

    Restricts both inputs to the dates they share **after** each has been
    reduced to its usable observations, then measures returns on the
    restricted series. Alignment has to come after that reduction: a
    non-positive price dropped from one series alone would re-introduce
    the very mismatch this prevents.

    With identical date sets, the calendar buckets and hence the measured
    intervals coincide, so the two lists are comparable position by
    position.
    """
    asset_points = usable_series(series, as_of)
    benchmark_points = usable_series(benchmark, as_of)

    shared = {point.date for point in asset_points} & {
        point.date for point in benchmark_points
    }
    asset_aligned = [point for point in asset_points if point.date in shared]
    benchmark_aligned = [point for point in benchmark_points if point.date in shared]

    return (
        _periodic_return_values(asset_aligned, periodicity, as_of),
        _periodic_return_values(benchmark_aligned, periodicity, as_of),
    )
