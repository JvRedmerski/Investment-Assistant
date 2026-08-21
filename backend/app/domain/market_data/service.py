"""Daily price ingestion.

Fetches OHLCV bars from a `MarketDataProvider`, runs them through the data
quality validator, and stores the ones that pass. This is the only code
path that calls the external provider — the read path
(`GET /assets/{ticker}/prices`) only ever reads from the database, so the
external API is never queried just because a user opened a page
(AGENTS.md rule 23).

Caching semantics: dates already stored for the asset are never
overwritten by a sync. If the provider's history genuinely needs to be
re-pulled for a given date (e.g. a correction), that is deliberately left
as a manual/future operation rather than silently overwriting historical
data (AGENTS.md rule 20 — data quality — cautions against blind
overwrites).
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.models.assets import Asset, AssetPrice
from app.domain.portfolio.valuation import ClosingPrice
from app.integrations.market_data.base import DailyHistoryProvider
from app.integrations.market_data.data_quality import validate_daily_bars

logger = logging.getLogger("investment_assistant.market_data.ingestion")


@dataclass
class PriceSyncResult:
    ticker: str
    start: date
    end: date
    fetched: int
    inserted: int
    skipped_existing: int
    rejected: int = 0


def sync_daily_history(
    db: Session,
    provider: DailyHistoryProvider,
    asset: Asset,
    start: date,
    end: date,
) -> PriceSyncResult:
    """Fetch [start, end] daily bars for `asset`, validate them, and insert
    the ones that are both valid and not already stored.

    Takes a `DailyHistoryProvider`, not a `MarketDataProvider`: ingestion
    needs closed bars and nothing else, so B3's open archive — which
    cannot quote — is as valid an input here as the vendor API.
    """
    bars = provider.get_daily_history(asset.ticker, start, end)

    quality_report = validate_daily_bars(
        bars, source_reports_adjusted_close=provider.reports_adjusted_close
    )
    for issue in quality_report.errors:
        logger.warning(
            "Rejected daily bar for %s on %s: %s (%s)",
            asset.ticker,
            issue.bar_date,
            issue.message,
            issue.code,
        )
    for issue in quality_report.warnings:
        logger.info(
            "Data quality warning for %s on %s: %s (%s)",
            asset.ticker,
            issue.bar_date,
            issue.message,
            issue.code,
        )

    existing_dates = {
        row.date
        for row in db.query(AssetPrice.date).filter(
            AssetPrice.asset_id == asset.id,
            AssetPrice.date >= start,
            AssetPrice.date <= end,
        )
    }

    inserted = 0
    skipped = 0
    for bar in quality_report.valid_bars:
        if bar.date in existing_dates:
            skipped += 1
            continue

        db.add(
            AssetPrice(
                asset_id=asset.id,
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                adjusted_close=bar.adjusted_close,
                volume=bar.volume,
                source=provider.source_name,
            )
        )
        inserted += 1

    db.commit()

    return PriceSyncResult(
        ticker=asset.ticker,
        start=start,
        end=end,
        fetched=len(bars),
        inserted=inserted,
        skipped_existing=skipped,
        rejected=quality_report.rejected_count,
    )


def latest_closes(
    db: Session, asset_ids: Iterable[int], as_of: date | None = None
) -> dict[int, ClosingPrice]:
    """The most recent stored close for each asset, on or before `as_of`.

    Reads only what is stored (rule 23): a screen opening never causes a
    call to the provider, so an asset nobody has synced simply has no
    entry here and the caller reports it as unvalued.

    `as_of` is honoured rather than ignored, because valuing a portfolio
    "as it stood in March" with a price from today is look-ahead in the
    same way a score reading a later filing is (rule 108).

    One query, not one per asset: the subquery picks each asset's newest
    qualifying date and the join takes that row. A portfolio of thirty
    holdings should not cost thirty round trips.
    """
    ids = list(asset_ids)
    if not ids:
        return {}

    newest = (
        select(
            AssetPrice.asset_id.label("asset_id"),
            func.max(AssetPrice.date).label("date"),
        )
        .where(AssetPrice.asset_id.in_(ids))
        .group_by(AssetPrice.asset_id)
    )
    if as_of is not None:
        newest = newest.where(AssetPrice.date <= as_of)
    newest = newest.subquery()

    rows = db.execute(
        select(AssetPrice).join(
            newest,
            (AssetPrice.asset_id == newest.c.asset_id)
            & (AssetPrice.date == newest.c.date),
        )
    ).scalars()

    return {row.asset_id: ClosingPrice(date=row.date, close=row.close) for row in rows}
