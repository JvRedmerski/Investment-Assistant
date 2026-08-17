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
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from app.data.models.assets import Asset, AssetPrice
from app.integrations.market_data.base import MarketDataProvider
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
    provider: MarketDataProvider,
    asset: Asset,
    start: date,
    end: date,
) -> PriceSyncResult:
    """Fetch [start, end] daily bars for `asset`, validate them, and insert
    the ones that are both valid and not already stored.
    """
    bars = provider.get_daily_history(asset.ticker, start, end)

    quality_report = validate_daily_bars(bars)
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
                source=settings.MARKET_DATA_PROVIDER,
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
