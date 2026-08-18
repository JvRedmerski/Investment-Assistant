"""A `FundamentalsProvider` that tries several sources in order.

The project has two sources with opposite strengths, and neither covers
the market on its own:

| | CVM | market data vendor |
|---|---|---|
| coverage | Brazilian `companhias abertas` only | BDRs, ETFs, foreign issuers too |
| depth | the filing itself, a decade back | whatever the plan includes |
| cost | free, no token, no quota | quota-limited, statements behind a paid tier |
| identity | CNPJ | ticker |

So the CVM leads and the vendor backs it up. An asset the CVM has never
heard of — a BDR, an ETF — falls through to the vendor, and if the
vendor's statement modules ever return, the fallback simply starts
working again with no change here.

## Whole periods only. Fields are never mixed between sources.

The tempting version of "merge" fills a gap in one source's statement
from the other's. This does not do that, deliberately.

Two providers computing the same figure from the same filing will still
disagree — over consolidated versus parent-only, over what counts as
debt, over which line is "revenue" for a bank. Splicing a vendor's equity
into the CVM's income statement would produce a row that no filing ever
reported, and the ROE derived from it would be an artefact of the seam.
Worse, nothing downstream could tell: the row would look like any other.

A period therefore comes wholly from one source. Where both have it, the
first provider listed wins.

## Failure is not a reason to fall through

`FundamentalsNotFoundError` means "this source has nothing for that
asset", which is exactly what a fallback is for. A timeout or an
unparseable payload means the source is broken, and quietly using the
other one would turn an outage into a silent change of source — the same
figures arriving from somewhere else, with nothing in the result to say
so. Those propagate.
"""

import logging
from contextlib import ExitStack

from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.exceptions import FundamentalsNotFoundError
from app.integrations.fundamentals.schemas import FinancialStatement

logger = logging.getLogger("investment_assistant.fundamentals.composite")


class CompositeFundamentalsProvider(FundamentalsProvider):
    """Delegates to each provider in turn until one has the asset."""

    def __init__(self, providers: list[FundamentalsProvider]) -> None:
        if not providers:
            raise ValueError("A composite provider needs at least one provider.")
        self._providers = providers

    def close(self) -> None:
        # `ExitStack` runs every callback even if one raises, so a
        # failure closing the first source cannot leak the others'
        # connections — and the failure still propagates.
        with ExitStack() as stack:
            for provider in self._providers:
                stack.callback(provider.close)

    def get_annual_statements(self, ticker: str) -> list[FinancialStatement]:
        for provider in self._providers:
            name = type(provider).__name__
            try:
                statements = provider.get_annual_statements(ticker)
            except FundamentalsNotFoundError:
                logger.info("%s has no statements for %s.", name, ticker)
                continue

            if statements:
                logger.info(
                    "%s supplied %s annual statement(s) for %s.",
                    name,
                    len(statements),
                    ticker,
                )
                return statements
            # An empty list is the same claim as "not found", made
            # without raising. Treated identically so a provider's choice
            # of signal cannot change which source ends up being used.
            logger.info("%s returned no statements for %s.", name, ticker)

        raise FundamentalsNotFoundError(
            f"No configured source has annual statements for {ticker}."
        )
