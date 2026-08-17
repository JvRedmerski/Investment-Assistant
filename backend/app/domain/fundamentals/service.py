"""Financial statement ingestion.

Same shape as `app.domain.market_data.service`: fetch from a
`FundamentalsProvider`, run the batch through the data quality
validator, and store only what passes. This is the only code path that
calls the external fundamentals provider — the read path
(`GET /assets/{ticker}/fundamentals`) only ever reads from the database
(AGENTS.md rule 23).

Caching semantics: a `reference_date` already stored for the asset is
never overwritten by a sync. This matters more here than it does for
prices. A company can restate a prior year, and a provider will then
serve the restated figure for that same period end. Silently replacing
the stored row would rewrite what the system "knew" at the time and
corrupt any later point-in-time analysis (AGENTS.md rules 108/109).
Handling restatements properly needs a schema that can hold more than
one version of a period, which the `fundamentals` table cannot today —
so the conservative choice is to keep the first value and leave
restatements as explicit future work.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.data.models.assets import Asset
from app.data.models.fundamentals import Fundamental
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.data_quality import validate_financial_statements

logger = logging.getLogger("investment_assistant.fundamentals.ingestion")


@dataclass
class FundamentalsSyncResult:
    ticker: str
    fetched: int
    inserted: int
    skipped_existing: int
    rejected: int = 0


def sync_annual_statements(
    db: Session,
    provider: FundamentalsProvider,
    asset: Asset,
) -> FundamentalsSyncResult:
    """Fetch annual statements for `asset`, validate them, and insert the
    ones that are both valid and not already stored.
    """
    statements = provider.get_annual_statements(asset.ticker)

    report = validate_financial_statements(statements)
    for issue in report.errors:
        logger.warning(
            "Rejected statement for %s at %s: %s (%s)",
            asset.ticker,
            issue.reference_date,
            issue.message,
            issue.code,
        )
    for issue in report.warnings:
        logger.info(
            "Data quality warning for %s at %s: %s (%s)",
            asset.ticker,
            issue.reference_date,
            issue.message,
            issue.code,
        )

    existing_dates = {
        row.reference_date
        for row in db.query(Fundamental.reference_date).filter(
            Fundamental.asset_id == asset.id
        )
    }

    inserted = 0
    skipped = 0
    for statement in report.valid_statements:
        if statement.reference_date in existing_dates:
            skipped += 1
            continue

        db.add(
            Fundamental(
                asset_id=asset.id,
                reference_date=statement.reference_date,
                revenue=statement.revenue,
                ebitda=statement.ebitda,
                net_income=statement.net_income,
                equity=statement.equity,
                debt=statement.debt,
                cash=statement.cash,
                free_cash_flow=statement.free_cash_flow,
            )
        )
        # Guard against a provider returning the same period twice across
        # separate pages/modules within one response.
        existing_dates.add(statement.reference_date)
        inserted += 1

    db.commit()

    return FundamentalsSyncResult(
        ticker=asset.ticker,
        fetched=len(statements),
        inserted=inserted,
        skipped_existing=skipped,
        rejected=report.rejected_count,
    )
