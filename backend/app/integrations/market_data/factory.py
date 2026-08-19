"""Selects the configured `MarketDataProvider` implementation.

Mirrors the `AIProvider` pattern from AGENTS.md rules 21/40: the rest of
the application depends only on `MarketDataProvider`; this factory is the
one place that knows which concrete class backs
`settings.MARKET_DATA_PROVIDER`, so a future provider can be added
without touching callers.
"""

from app.core.config import settings
from app.integrations.market_data.base import DailyHistoryProvider, MarketDataProvider
from app.integrations.market_data.brapi import BrapiProvider
from app.integrations.market_data.cotahist import B3CotahistProvider


def build_market_data_provider() -> MarketDataProvider:
    provider_name = settings.MARKET_DATA_PROVIDER.lower()
    if provider_name == "brapi":
        return BrapiProvider()
    raise ValueError(f"Unknown MARKET_DATA_PROVIDER: {settings.MARKET_DATA_PROVIDER!r}")


def build_historical_price_provider() -> DailyHistoryProvider:
    """Selects the source used to backfill deep price history.

    Separate from `build_market_data_provider` because the two answer
    different questions and are not interchangeable: the vendor quotes
    and serves a short recent window, while B3's open archive serves
    decades and cannot quote at all (rule 21).
    """
    provider_name = settings.HISTORICAL_PRICE_PROVIDER.lower()
    if provider_name == "b3_cotahist":
        return B3CotahistProvider()
    if provider_name == "brapi":
        return BrapiProvider()
    raise ValueError(
        f"Unknown HISTORICAL_PRICE_PROVIDER: {settings.HISTORICAL_PRICE_PROVIDER!r}"
    )
