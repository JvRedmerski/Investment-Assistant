"""Running a backtest against the stored data, and reporting it honestly.

The I/O side of the wave: loads prices, corporate actions and the
universe, hands them to the pure engine, and measures the result with the
same code that measures the investor's own portfolio.

## Two prices, two questions, and neither one substitutes for the other

The **simulation** runs on raw closes, with payouts arriving separately
as cash. That is the investor's world, and it is the only combination
that does not double count (see `simulation`).

The **performance index** runs on `adjusted_close`, because a return
series has no other valid input. Rule 26 is why it is time-weighted at
all: `(final - initial) / initial` over a portfolio fed R$ 1.000 a month
reports a gain in a year the investor lost money.

The **wealth curve** runs on raw closes again, and adds the cash the
strategy did not spend. Leaving that out would understate the portfolio
by exactly the money the strategy chose to hold, which is a result and
not an absence.

## Where the total-return series stops, the backtest stops with it

`adjusted_close` exists only where the adjustment is **complete**: every
session B3's counter marked ex must have a sized action behind it, or the
series ends there (ADR-026). That truncation is not only a measurement
problem. A session marked ex with no action behind it is a distribution
this project cannot size, so a simulation running through it credits less
cash than the investor received — and the run would be wrong, not merely
unmeasurable.

So the window starts at the latest date from which **every** asset in the
universe has a complete series, and the result names the asset and the
date that bound it. Conservative on purpose: the alternative is a run
that looks longer and is quietly missing payouts.

An asset with no complete series at all is **excluded** rather than
allowed to bound the window to nothing, and the exclusion is named. It is
the same call as excluding an asset with no stored price: keeping it
would make every backtest impossible instead of making one of them
smaller, and a named exclusion is visible where a silent one would not
be (rule 59 is about not reconstructing the past from today's winners,
which naming an unmeasurable asset is not).

## What this reports that a single number would hide

`comparison` is the index against a benchmark — time-weighted, so
contributions are neutralised and the figure is comparable with the CDI
or the Ibovespa. `wealth` is the money: what went in, what it is worth,
and the cash sitting between them. The two disagree by design, and both
are needed — ADR-019 exists because patrimonial growth read as
performance is the reading this project keeps guarding against.

⚠️ **The index assumes each payout was reinvested when it went ex**,
because that is what `adjusted_close` means. The simulation actually
reinvests it at the next contribution, and holds it as cash until then.
So the index slightly overstates a strategy that lets dividends sit, and
`wealth` is where that drag is visible. The same assumption is already in
the live dashboard (`portfolio.performance`), which is why it is stated
here rather than fixed here — a money-weighted return is Future Work, and
it belongs to both callers or to neither.

Nothing here is stored (rule 16). A backtest is derived, like positions
and plans.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models.assets import Asset, AssetPrice
from app.data.models.assets import CorporateAction as StoredAction
from app.domain.backtesting.availability import PUBLICATION_LAG_MONTHS
from app.domain.backtesting.metrics import TradeStatistics, trade_statistics
from app.domain.backtesting.schemas import ZERO, CostModel, Decision, Simulation
from app.domain.backtesting.simulation import (
    CashAction,
    ContributionSchedule,
    simulate,
)
from app.domain.backtesting.universe import contribution_strategy, rebalancing_strategy
from app.domain.benchmarks.catalog import BenchmarkDefinition
from app.domain.benchmarks.comparison import BenchmarkComparison, align, compare
from app.domain.benchmarks.service import benchmark_price_points, risk_free_rate_for
from app.domain.market_data.corporate_actions import share_adjustments
from app.domain.market_data.series import adjusted_closes_by_asset, closes_by_asset
from app.domain.portfolio.performance import performance_index, value_series
from app.domain.recommendations.allocation import DEFAULT_POLICY, AllocationPolicy
from app.quant.returns import Periodicity, PricePoint
from app.quant.risk import alpha as jensens_alpha

#: The strategies a backtest may be asked to run, by name.
#:
#: A closed list rather than an arbitrary callable: every one of these is
#: a plan this project actually produces, and a backtest of anything else
#: would be measuring code that does not run in production.
STRATEGIES = {
    "contribution-plan": contribution_strategy,
    "rebalance-plan": rebalancing_strategy,
}

#: B3's own fee rate and no brokerage — the honest default for the
#: Brazilian retail broker this project is written for, and still a
#: choice every result carries with it (rule 107).
DEFAULT_COSTS = CostModel()

#: Why an asset was left out of the universe it was offered for.
NO_PRICES = "NO_PRICES"
NO_TOTAL_RETURN_SERIES = "NO_TOTAL_RETURN_SERIES"


@dataclass(frozen=True)
class BacktestSettings:
    """Everything a run is parameterised by, echoed back with the result.

    Carried whole rather than summarised, because a figure that cannot
    say which assumptions produced it is not reproducible (rule 113) —
    and because every one of these is a *choice*, from the fee rate to
    the publication lag.
    """

    start: date
    end: date
    strategy: str
    contribution: Decimal
    day_of_month: int = 1
    costs: CostModel = DEFAULT_COSTS
    policy: AllocationPolicy = DEFAULT_POLICY
    publication_lag_months: int = PUBLICATION_LAG_MONTHS


@dataclass(frozen=True)
class WealthPoint:
    """What the run was worth on one date, and what it had been given.

    `holdings` is priced at the raw close; `cash` is what the strategy
    had not spent. `contributed` is the money paid in by that date, which
    is the line that stops the total being read as performance (ADR-019).
    """

    date: date
    holdings: Decimal
    cash: Decimal
    total: Decimal
    contributed: Decimal


@dataclass(frozen=True)
class BacktestWindow:
    """The period asked for, the period run, and what shortened it."""

    requested_start: date
    requested_end: date
    start: date
    end: date
    #: Ticker whose total-return series starts latest, when that is what
    #: moved `start`. `None` when the requested start was usable as is.
    bounded_by: str | None = None


@dataclass(frozen=True)
class BacktestResult:
    """One replay, with everything needed to read it and to repeat it."""

    settings: BacktestSettings
    window: BacktestWindow
    universe: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]
    comparison: BenchmarkComparison | None
    #: Jensen's alpha over the window the two series share. `None` when
    #: beta, either return or the risk-free rate is missing.
    alpha: Decimal | None
    index: tuple[PricePoint, ...]
    wealth: tuple[WealthPoint, ...]
    trades: TradeStatistics
    decisions: tuple[Decision, ...]
    sources: tuple[str, ...] = ()

    @property
    def final(self) -> WealthPoint | None:
        return self.wealth[-1] if self.wealth else None


def run_backtest(
    db: Session,
    assets: Sequence[Asset],
    settings: BacktestSettings,
    definition: BenchmarkDefinition | None = None,
) -> BacktestResult:
    """Replay `settings.strategy` over `assets` and measure what happened.

    `assets` is the universe as offered; what is actually testable comes
    back in `universe`, and what was dropped in `excluded`.
    """
    if settings.strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {settings.strategy}")

    rows = _price_rows(db, assets, settings.end)
    testable, excluded, bounded_by, complete_from = _testable_universe(assets, rows)

    start = max(settings.start, complete_from) if complete_from else settings.start
    window = BacktestWindow(
        requested_start=settings.start,
        requested_end=settings.end,
        start=start,
        end=settings.end,
        bounded_by=(
            bounded_by if complete_from and complete_from > settings.start else None
        ),
    )

    if not testable or start > settings.end:
        return _empty(settings, window, testable, excluded)

    asset_ids = [asset.id for asset in testable]
    testable_ids = set(asset_ids)
    usable = [row for row in rows if row.asset_id in testable_ids]
    actions = share_adjustments(db, asset_ids, settings.end)

    run = simulate(
        start=start,
        end=settings.end,
        schedule=ContributionSchedule(
            amount=settings.contribution, day_of_month=settings.day_of_month
        ),
        strategy=STRATEGIES[settings.strategy](
            db,
            testable,
            policy=settings.policy,
            publication_lag_months=settings.publication_lag_months,
        ),
        closes=closes_by_asset(usable),
        cash_actions=_cash_actions(db, asset_ids, start, settings.end),
        share_actions=actions,
        costs=settings.costs,
    )

    ledger = list(run.transactions)
    index = performance_index(
        ledger,
        adjusted_closes_by_asset(usable),
        as_of=settings.end,
        adjustments=actions,
    )
    wealth = _wealth(
        value_series(ledger, closes_by_asset(usable), settings.end, actions), run
    )

    comparison = None
    measured_alpha = None
    if definition is not None:
        benchmark = benchmark_price_points(db, definition, start, settings.end)
        risk_free = risk_free_rate_for(db, start, settings.end)
        comparison = compare(
            index,
            benchmark,
            definition,
            risk_free_rate=risk_free,
            periodicity=Periodicity.DAILY,
            as_of=settings.end,
        )
        # Alpha is measured on the same shared window `compare` used, and
        # not on the two series as they arrived: a subject and a benchmark
        # covering different periods are not comparable at all (rule 28).
        shared = align(index, benchmark or None)
        measured_alpha = jensens_alpha(
            list(shared.subject),
            list(shared.benchmark) or None,
            risk_free,
            Periodicity.DAILY,
            settings.end,
        )

    return BacktestResult(
        settings=settings,
        window=window,
        universe=tuple(asset.ticker for asset in testable),
        excluded=excluded,
        comparison=comparison,
        alpha=measured_alpha,
        index=tuple(index),
        wealth=wealth,
        trades=trade_statistics(run),
        decisions=run.decisions,
        sources=tuple(sorted({row.source for row in usable})),
    )


# -- loading ----------------------------------------------------------


def _price_rows(db: Session, assets: Sequence[Asset], end: date) -> list[AssetPrice]:
    """Every stored bar for the universe, up to `end` (rule 108).

    Loaded once and split two ways by `market_data.series` — raw closes
    for execution and for the wealth curve, adjusted ones for the index.
    Reading them from one query is what keeps the two maps describing the
    same sessions.

    Not filtered by the requested start: the window may only be shortened
    by what the data supports, and deciding that needs the rows before it.
    """
    ids = [asset.id for asset in assets]
    if not ids:
        return []
    return (
        db.query(AssetPrice)
        .filter(AssetPrice.asset_id.in_(ids), AssetPrice.date <= end)
        .order_by(AssetPrice.asset_id, AssetPrice.date)
        .all()
    )


def _cash_actions(
    db: Session, asset_ids: Sequence[int], start: date, end: date
) -> list[CashAction]:
    """Every payout in the window, in reais per share.

    Only the rows carrying a `cash_amount`: an action that moves the
    share count reaches the simulation through `share_adjustments`
    instead, and a row is never both (`CorporateAction`).
    """
    if not asset_ids:
        return []
    stored = (
        db.query(StoredAction)
        .filter(
            StoredAction.asset_id.in_(list(asset_ids)),
            StoredAction.cash_amount.is_not(None),
            StoredAction.ex_date >= start,
            StoredAction.ex_date <= end,
        )
        .order_by(StoredAction.ex_date, StoredAction.id)
        .all()
    )
    return [
        CashAction(
            asset_id=action.asset_id,
            ex_date=action.ex_date,
            amount_per_share=action.cash_amount,
            label=action.label,
        )
        for action in stored
    ]


# -- what can be tested, and from when --------------------------------


def _testable_universe(
    assets: Sequence[Asset], rows: Sequence[AssetPrice]
) -> tuple[list[Asset], tuple[tuple[str, str], ...], str | None, date | None]:
    """Split the offered universe into what can be replayed and what cannot.

    Returns the testable assets, the named exclusions, the ticker whose
    total-return series starts latest, and that date — which is the
    earliest the whole universe can be simulated from.
    """
    by_asset: dict[int, list[AssetPrice]] = {}
    for row in rows:
        by_asset.setdefault(row.asset_id, []).append(row)

    testable: list[Asset] = []
    excluded: list[tuple[str, str]] = []
    latest: date | None = None
    bounded_by: str | None = None

    for asset in assets:
        bars = by_asset.get(asset.id)
        if not bars:
            excluded.append((asset.ticker, NO_PRICES))
            continue

        complete_from = _complete_from(bars)
        if complete_from is None:
            excluded.append((asset.ticker, NO_TOTAL_RETURN_SERIES))
            continue

        testable.append(asset)
        if latest is None or complete_from > latest:
            latest = complete_from
            bounded_by = asset.ticker

    return testable, tuple(excluded), bounded_by, latest


def _complete_from(bars: Sequence[AssetPrice]) -> date | None:
    """The first session after this asset's last unadjustable one.

    Not simply the earliest row carrying an `adjusted_close`: a series can
    be adjusted, interrupted and adjusted again — a vendor's own figures
    for recent sessions sitting above sessions that were never derived —
    and the part before the last gap is not a total-return series, however
    many values it holds.

    `None` when no session is adjustable at all.
    """
    ordered = sorted(bars, key=lambda bar: bar.date)
    last_gap: date | None = None
    for bar in ordered:
        if bar.adjusted_close is None:
            last_gap = bar.date

    for bar in ordered:
        if last_gap is None or bar.date > last_gap:
            return bar.date
    return None


# -- assembling -------------------------------------------------------


def _wealth(points: Sequence, run: Simulation) -> tuple[WealthPoint, ...]:
    """The value curve with the run's cash balance and contribution line.

    Three quantities on one date, and the third is what stops the first
    being read as performance: a total that doubled because R$ 1.000
    arrived every month looks identical to one that doubled on returns
    until the contribution line is under it (ADR-019).
    """
    paid_in = _contributions_by_date(run)
    wealth: list[WealthPoint] = []
    contributed = ZERO
    remaining = list(paid_in)

    for point in points:
        while remaining and remaining[0][0] <= point.date:
            contributed += remaining.pop(0)[1]
        cash = run.cash_on(point.date)
        wealth.append(
            WealthPoint(
                date=point.date,
                holdings=point.value,
                cash=cash,
                total=point.value + cash,
                contributed=contributed,
            )
        )
    return tuple(wealth)


def _contributions_by_date(run: Simulation) -> list[tuple[date, Decimal]]:
    """Each deposit and the day it landed, oldest first.

    Read from the ledger rather than from `Simulation.contributed`, which
    is the total for the whole run: the wealth curve needs the line as it
    stood on each date, not a horizontal one at the final figure.
    """
    deposits: list[tuple[date, Decimal]] = []
    for transaction in run.transactions:
        if transaction.asset_id is None:
            deposits.append(
                (
                    transaction.transaction_date.date(),
                    transaction.quantity * transaction.price,
                )
            )
    deposits.sort(key=lambda item: item[0])
    return deposits


def _empty(
    settings: BacktestSettings,
    window: BacktestWindow,
    testable: Sequence[Asset],
    excluded: tuple[tuple[str, str], ...],
) -> BacktestResult:
    """A run that could not happen, saying so rather than returning zeros."""
    return BacktestResult(
        settings=settings,
        window=window,
        universe=tuple(asset.ticker for asset in testable),
        excluded=excluded,
        comparison=None,
        alpha=None,
        index=(),
        wealth=(),
        trades=trade_statistics(Simulation(transactions=(), adjustments=())),
        decisions=(),
    )
