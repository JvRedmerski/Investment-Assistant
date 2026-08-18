"""Benchmark series ingestion.

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
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.data.models.benchmarks import BenchmarkValue
from app.domain.benchmarks.catalog import BenchmarkDefinition
from app.domain.benchmarks.data_quality import validate_benchmark_series
from app.integrations.benchmarks.base import BenchmarkProvider

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
