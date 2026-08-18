"""Selects the configured `FundamentalsProvider` implementation.

Same pattern as `app.integrations.market_data.factory` (AGENTS.md rules
21/40): the rest of the application depends only on the abstract type;
this factory is the single place that knows which concrete class backs
`settings.FUNDAMENTALS_PROVIDER`.

The default is the composite, because neither source covers the market
alone — see `composite.py` for the table.
"""

from app.core.config import settings
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.brapi import BrapiFundamentalsProvider
from app.integrations.fundamentals.composite import CompositeFundamentalsProvider
from app.integrations.fundamentals.cvm import CnpjResolver, CvmFundamentalsProvider
from app.integrations.fundamentals.identity import BrapiCnpjResolver


def build_fundamentals_provider(
    resolve_cnpj: CnpjResolver | None = None,
) -> FundamentalsProvider:
    """The configured provider.

    `resolve_cnpj` lets a caller supply a ticker-to-CNPJ lookup that
    reads what is already stored on the asset, instead of spending a
    request per ticker. Omitted, the vendor's profile module is asked
    directly.
    """
    provider_name = settings.FUNDAMENTALS_PROVIDER.lower()

    if provider_name == "brapi":
        return BrapiFundamentalsProvider()
    if provider_name == "cvm":
        return CvmFundamentalsProvider(resolve_cnpj or BrapiCnpjResolver())
    if provider_name == "cvm_then_brapi":
        return CompositeFundamentalsProvider(
            [
                CvmFundamentalsProvider(resolve_cnpj or BrapiCnpjResolver()),
                BrapiFundamentalsProvider(),
            ]
        )
    raise ValueError(
        f"Unknown FUNDAMENTALS_PROVIDER: {settings.FUNDAMENTALS_PROVIDER!r}"
    )
