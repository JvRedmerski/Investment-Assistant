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
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models.assets import Asset, AssetPrice
from app.data.models.fundamentals import FinancialIndicator, Fundamental
from app.domain.fundamentals.indicators import (
    IndicatorInputs,
    compute_indicators,
)
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
                ebit=statement.ebit,
                income_before_tax=statement.income_before_tax,
                income_tax_expense=statement.income_tax_expense,
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


@dataclass
class IndicatorsComputeResult:
    ticker: str
    periods: int
    computed: int
    skipped_existing: int
    recomputed: bool = False


def compute_and_store_indicators(
    db: Session, asset: Asset, recompute: bool = False
) -> IndicatorsComputeResult:
    """Derive `financial_indicators` rows from stored statements and prices.

    Purely a transformation of data already held: this never calls an
    external provider.

    By default, periods already present are left untouched. Passing
    `recompute=True` discards this asset's stored indicators and rebuilds
    them from the current inputs and formulas.

    Why recomputation is allowed here, when a stored *statement* is never
    overwritten (ADR-013): a statement is a reported fact, and replacing
    it would rewrite what the source said. An indicator is a pure
    function of stored inputs and the current code — when a formula is
    corrected or an input arrives that was missing, the old value is
    simply wrong, and preserving it would be preserving a bug. The raw
    statements are untouched either way, so nothing reported is lost.
    It stays opt-in rather than automatic (ADR-015).

    Growth indicators use the immediately preceding stored statement.
    Because statements are replayed in chronological order, the "previous
    period" is always genuinely earlier, never a later one.
    """
    statements = (
        db.query(Fundamental)
        .filter(Fundamental.asset_id == asset.id)
        .order_by(Fundamental.reference_date)
        .all()
    )

    if recompute:
        # "fetch" evicts the deleted rows from the session's identity map.
        # With synchronize_session=False they would linger there, and the
        # rows inserted below could collide with them on primary key.
        deleted = (
            db.query(FinancialIndicator)
            .filter(FinancialIndicator.asset_id == asset.id)
            .delete(synchronize_session="fetch")
        )
        logger.info(
            "Recomputing indicators for %s: discarded %s stored row(s).",
            asset.ticker,
            deleted,
        )
        existing_dates: set = set()
    else:
        existing_dates = {
            row.reference_date
            for row in db.query(FinancialIndicator.reference_date).filter(
                FinancialIndicator.asset_id == asset.id
            )
        }

    computed = 0
    skipped = 0
    previous_inputs: IndicatorInputs | None = None

    for statement in statements:
        inputs = _inputs_from(db, asset, statement)

        if statement.reference_date in existing_dates:
            skipped += 1
            # Still carry this period forward: the next period's growth
            # must compare against it even though it was not recomputed.
            previous_inputs = inputs
            continue

        indicators = compute_indicators(inputs, previous_inputs)
        db.add(
            FinancialIndicator(
                asset_id=asset.id,
                reference_date=statement.reference_date,
                pe=indicators.pe,
                pb=indicators.pb,
                roe=indicators.roe,
                roic=indicators.roic,
                dy=indicators.dy,
                debt_ebitda=indicators.debt_ebitda,
                net_margin=indicators.net_margin,
                ebitda_margin=indicators.ebitda_margin,
                revenue_growth=indicators.revenue_growth,
                profit_growth=indicators.profit_growth,
            )
        )
        existing_dates.add(statement.reference_date)
        computed += 1
        previous_inputs = inputs

    db.commit()

    return IndicatorsComputeResult(
        ticker=asset.ticker,
        periods=len(statements),
        computed=computed,
        skipped_existing=skipped,
        recomputed=recompute,
    )


def _inputs_from(db: Session, asset: Asset, statement: Fundamental) -> IndicatorInputs:
    return IndicatorInputs(
        reference_date=statement.reference_date,
        revenue=statement.revenue,
        ebitda=statement.ebitda,
        net_income=statement.net_income,
        equity=statement.equity,
        debt=statement.debt,
        cash=statement.cash,
        free_cash_flow=statement.free_cash_flow,
        ebit=statement.ebit,
        income_before_tax=statement.income_before_tax,
        income_tax_expense=statement.income_tax_expense,
        price=_price_on_or_before(db, asset.id, statement.reference_date),
    )


def _price_on_or_before(
    db: Session, asset_id: int, reference_date: date
) -> Decimal | None:
    """The latest stored close at or before `reference_date`.

    Selecting the *nearest earlier* close rather than the nearest close
    outright is the whole point: a price from after the reference date
    was not knowable then, and using it would leak future information
    into any indicator derived from it (AGENTS.md rule 108). Returns
    `None` when no price at or before that date is stored.
    """
    row = (
        db.query(AssetPrice.close)
        .filter(
            AssetPrice.asset_id == asset_id,
            AssetPrice.date <= reference_date,
        )
        .order_by(AssetPrice.date.desc())
        .first()
    )
    return row.close if row is not None else None
