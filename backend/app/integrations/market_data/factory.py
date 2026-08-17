"""Selects the configured `MarketDataProvider` implementation.

Mirrors the `AIProvider` pattern from AGENTS.md rules 21/40: the rest of
the application depends only on `MarketDataProvider`; this factory is the
one place that knows which concrete class backs
`settings.MARKET_DATA_PROVIDER`, so a future provider can be added
without touching callers.
"""

from app.core.config import settings
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.brapi import BrapiProvider


def build_market_data_provider() -> MarketDataProvider:
    provider_name = settings.MARKET_DATA_PROVIDER.lower()
    if provider_name == "brapi":
        return BrapiProvider()
    raise ValueError(f"Unknown MARKET_DATA_PROVIDER: {settings.MARKET_DATA_PROVIDER!r}")
