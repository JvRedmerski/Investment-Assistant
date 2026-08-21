"""Benchmark series ingestion, and the database side of comparison.

The same shape as `market_data.service`, and for the same reasons: this
is the only code path that calls an external source, the read path only
ever queries the database, and a date already stored is never overwritten
(AGENTS.md rules 20 and 23).

Idempotence matters more here than it does for prices, because a
benchmark series is the *denominator* of every comparison the product
makes. If a CDI observation were rewritten on a later sync, every
previously reported "portfolio versus CDI" figure would silently stop
reproducing, with nothing in the output to show that the reference moved
rather than the portfolio.

The second half of this module assembles a comparison: it loads a
subject series and a benchmark series out of the database, converts each
into the `PricePoint` shape `app.quant` reads, and hands both to
`comparison.compare`, which is pure. Nothing is calculated here.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models.assets import Asset, AssetPrice
from app.data.models.benchmarks import BenchmarkValue
from app.data.models.portfolio import Portfolio, Transaction
from app.domain.benchmarks.catalog import CDI, BenchmarkDefinition
from app.domain.benchmarks.comparison import (
    AlignedSeries,
    BenchmarkComparison,
    SeriesPerformance,
    align,
    compare,
    summarise,
)
from app.domain.benchmarks.data_quality import validate_benchmark_series
from app.domain.benchmarks.series import annualised_rate, to_price_points
from app.domain.market_data.series import (
    adjusted_closes_by_asset,
    adjusted_price_points,
    closes_by_asset,
)
from app.domain.portfolio.performance import (
    ValuePoint,
    performance_index,
    value_series,
)
from app.integrations.benchmarks.base import BenchmarkProvider
from app.quant.returns import Periodicity, PricePoint

logger = logging.getLogger("investment_assistant.benchmarks.ingestion")


@dataclass
class BenchmarkSyncResult:
    code: str
    start: date
    end: date
    fetched: int
    inserted: int
    skipped_existing: int
    rejected: int = 0


def sync_benchmark_series(
    db: Session,
    provider: BenchmarkProvider,
    definition: BenchmarkDefinition,
    start: date,
    end: date,
    today: date | None = None,
) -> BenchmarkSyncResult:
    """Fetch [start, end] for `definition`, validate, and insert what is new.

    `today` decides which periods count as finished; it defaults to the
    system date and is injectable so the boundary is testable without
    mocking a clock. Everything else about the decision lives in
    `validate_benchmark_series`.

    A `rejected` count of one on a daily sync is routine, not a fault: it
    is usually the period in progress, which the next run picks up once
    the source publishes a settled figure.
    """
    reference_day = today or datetime.now(UTC).date()

    observations = provider.get_series(
        definition.series_id, start, end, definition.kind
    )

    report = validate_benchmark_series(observations, definition, reference_day)
    for issue in report.errors:
        logger.warning(
            "Rejected %s observation for %s: %s (%s)",
            definition.code,
            issue.observation_date,
            issue.message,
            issue.code,
        )
    for issue in report.warnings:
        logger.info(
            "Data quality warning for %s on %s: %s (%s)",
            definition.code,
            issue.observation_date,
            issue.message,
            issue.code,
        )

    existing_dates = {
        row.date
        for row in db.query(BenchmarkValue.date).filter(
            BenchmarkValue.benchmark_code == definition.code,
            BenchmarkValue.date >= start,
            BenchmarkValue.date <= end,
        )
    }

    inserted = 0
    skipped = 0
    for observation in report.valid_observations:
        if observation.date in existing_dates:
            skipped += 1
            continue
        db.add(
            BenchmarkValue(
                benchmark_code=definition.code,
                date=observation.date,
                value=observation.value,
                source=definition.source.value,
            )
        )
        inserted += 1

    db.commit()

    return BenchmarkSyncResult(
        code=definition.code,
        start=start,
        end=end,
        fetched=len(observations),
        inserted=inserted,
        skipped_existing=skipped,
        rejected=report.rejected_count,
    )


def read_benchmark_values(
    db: Session,
    definition: BenchmarkDefinition,
    start: date | None = None,
    end: date | None = None,
) -> list[BenchmarkValue]:
    """Stored observations for `definition`, oldest first.

    Reads only from the database — opening a page never triggers a call
    to an external source (AGENTS.md rule 23).
    """
    query = db.query(BenchmarkValue).filter(
        BenchmarkValue.benchmark_code == definition.code
    )
    if start is not None:
        query = query.filter(BenchmarkValue.date >= start)
    if end is not None:
        query = query.filter(BenchmarkValue.date <= end)
    return query.order_by(BenchmarkValue.date).all()


# -- comparison ------------------------------------------------------


def benchmark_price_points(
    db: Session,
    definition: BenchmarkDefinition,
    start: date | None = None,
    end: date | None = None,
) -> list[PricePoint]:
    """The stored benchmark series as a level series (see `series.py`)."""
    return to_price_points(
        read_benchmark_values(db, definition, start, end), definition
    )


def risk_free_rate_for(
    db: Session,
    start: date | None = None,
    end: date | None = None,
) -> Decimal | None:
    """The CDI over the window, as an annual fraction.

    The CDI rather than a configurable choice: it is *the* risk-free
    reference in Brazil, and `sharpe`/`sortino` want one number, not a
    preference. `None` when no CDI has been ingested for the window, in
    which case those two ratios stay `None` rather than being computed
    against an assumed zero.
    """
    return annualised_rate(read_benchmark_values(db, CDI, start, end), CDI)


def compare_asset_with_benchmark(
    db: Session,
    asset: Asset,
    definition: BenchmarkDefinition,
    start: date | None = None,
    end: date | None = None,
) -> BenchmarkComparison:
    """One asset's stored price history against a benchmark."""
    query = db.query(AssetPrice).filter(AssetPrice.asset_id == asset.id)
    if start is not None:
        query = query.filter(AssetPrice.date >= start)
    if end is not None:
        query = query.filter(AssetPrice.date <= end)

    subject = adjusted_price_points(query.order_by(AssetPrice.date))
    return _compare(db, subject, definition, start, end)


def compare_portfolio_with_benchmark(
    db: Session,
    portfolio: Portfolio,
    definition: BenchmarkDefinition,
    start: date | None = None,
    end: date | None = None,
) -> BenchmarkComparison:
    """A portfolio's time-weighted performance against a benchmark.

    The whole ledger is replayed, not only the part inside [start, end]:
    holdings on the first day of the window are the product of every
    transaction before it, so truncating the ledger would value the
    portfolio as if it had been bought on the window's first day. Only
    the *valuation* is windowed.
    """
    transactions = (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == portfolio.id)
        .order_by(Transaction.transaction_date, Transaction.id)
        .all()
    )
    asset_ids = {tx.asset_id for tx in transactions if tx.asset_id is not None}

    prices: dict[int, dict[date, Decimal]] = {}
    if asset_ids:
        price_query = db.query(AssetPrice).filter(AssetPrice.asset_id.in_(asset_ids))
        if start is not None:
            price_query = price_query.filter(AssetPrice.date >= start)
        if end is not None:
            price_query = price_query.filter(AssetPrice.date <= end)
        prices = adjusted_closes_by_asset(price_query)

    subject = performance_index(transactions, prices, as_of=end)
    return _compare(db, subject, definition, start, end)


@dataclass(frozen=True)
class PortfolioSeries:
    """Everything one evolution chart needs, loaded once.

    `value` is the wealth curve — raw closes, contributions included —
    and `aligned` holds the time-weighted index against the benchmark,
    both rebased to the same date and level. They are returned together
    because a chart that shows one without the other invites the reading
    ADR-019 exists to prevent: patrimonial growth read as performance.
    """

    value: list[ValuePoint]
    aligned: AlignedSeries
    subject: SeriesPerformance
    benchmark: SeriesPerformance | None
    definition: BenchmarkDefinition | None
    sources: tuple[str, ...]


def portfolio_series(
    db: Session,
    portfolio: Portfolio,
    definition: BenchmarkDefinition | None = None,
    start: date | None = None,
    end: date | None = None,
) -> PortfolioSeries:
    """The two series a dashboard draws, plus what labels them.

    The whole ledger is replayed and only the *valuation* is windowed,
    for the reason `compare_portfolio_with_benchmark` gives: holdings on
    the window's first day are the product of every transaction before
    it.

    Two price maps are loaded from the same rows — raw closes for the
    wealth curve, adjusted ones for the index — because they answer
    different questions and `market_data.series` is the only place
    allowed to tell them apart.

    `sources` names where the prices came from, which rule 74 requires a
    chart to be able to state.
    """
    transactions = (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == portfolio.id)
        .order_by(Transaction.transaction_date, Transaction.id)
        .all()
    )
    asset_ids = {tx.asset_id for tx in transactions if tx.asset_id is not None}

    rows: list[AssetPrice] = []
    if asset_ids:
        price_query = db.query(AssetPrice).filter(AssetPrice.asset_id.in_(asset_ids))
        if start is not None:
            price_query = price_query.filter(AssetPrice.date >= start)
        if end is not None:
            price_query = price_query.filter(AssetPrice.date <= end)
        rows = price_query.all()

    index = performance_index(transactions, adjusted_closes_by_asset(rows), as_of=end)
    wealth = value_series(transactions, closes_by_asset(rows), as_of=end)

    benchmark_points: list[PricePoint] = []
    if definition is not None:
        benchmark_points = to_price_points(
            read_benchmark_values(db, definition, start, end), definition
        )

    aligned = align(index, benchmark_points or None)

    return PortfolioSeries(
        value=wealth,
        aligned=aligned,
        # Summarised over the window that is actually drawn, so the
        # figure beside a chart describes the chart. Asking for a
        # benchmark narrows both; asking for none leaves the whole
        # history, since there is nothing to share a window with.
        subject=summarise(list(aligned.subject), Periodicity.DAILY, end),
        benchmark=(
            summarise(list(aligned.benchmark), definition.periodicity, end)
            if definition is not None
            else None
        ),
        definition=definition,
        sources=tuple(sorted({row.source for row in rows})),
    )


def _compare(
    db: Session,
    subject: list[PricePoint],
    definition: BenchmarkDefinition,
    start: date | None,
    end: date | None,
) -> BenchmarkComparison:
    return compare(
        subject,
        benchmark_price_points(db, definition, start, end),
        definition,
        risk_free_rate=risk_free_rate_for(db, start, end),
        periodicity=Periodicity.DAILY,
        as_of=end,
    )
