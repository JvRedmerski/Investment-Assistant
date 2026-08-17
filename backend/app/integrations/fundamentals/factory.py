"""Selects the configured `FundamentalsProvider` implementation.

Same pattern as `app.integrations.market_data.factory` (AGENTS.md rules
21/40): the rest of the application depends only on the abstract type;
this factory is the single place that knows which concrete class backs
`settings.FUNDAMENTALS_PROVIDER`.
"""

from app.core.config import settings
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.brapi import BrapiFundamentalsProvider


def build_fundamentals_provider() -> FundamentalsProvider:
    provider_name = settings.FUNDAMENTALS_PROVIDER.lower()
    if provider_name == "brapi":
        return BrapiFundamentalsProvider()
    raise ValueError(
        f"Unknown FUNDAMENTALS_PROVIDER: {settings.FUNDAMENTALS_PROVIDER!r}"
    )
