"""Daily price ingestion.

Fetches OHLCV bars from a `MarketDataProvider` and stores them in
`asset_prices`. This is the only code path that calls the external
provider — the read path (`GET /assets/{ticker}/prices`) only ever reads
from the database, so the external API is never queried just because a
user opened a page (AGENTS.md rule 23).

Caching semantics: dates already stored for the asset are never
overwritten by a sync. If the provider's history genuinely needs to be
re-pulled for a given date (e.g. a correction), that is deliberately left
as a manual/future operation rather than silently overwriting historical
data (AGENTS.md rule 20 — data quality — cautions against blind
overwrites).
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from app.data.models.assets import Asset, AssetPrice
from app.integrations.market_data.base import MarketDataProvider


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
    """Fetch [start, end] daily bars for `asset` and insert the ones not
    already stored. Returns counts; never raises on individual bad bars
    today (see W05-003 for the dedicated data quality validator that will
    populate `rejected`).
    """
    bars = provider.get_daily_history(asset.ticker, start, end)

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
    for bar in bars:
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
    )
