"""Resolving a B3 ticker to the CNPJ the CVM files it under.

This module is the joint between the two fundamentals sources, and the
reason the project can use both at once:

- the **market data vendor** knows tickers. It still serves
  `summaryProfile` on the free plan, and that module carries the
  company's CNPJ — verified live on 2026-08-18, where `PETR4` returned
  `33000167000101`.
- the **CVM** knows CNPJs and nothing else. Its files have no ticker
  column at all.

Neither source can answer the question alone. Together they can, and
that is the whole of the merge: identity from the vendor, figures from
the regulator.

## Why the answer is worth storing

Resolving costs a request against a quota-limited plan, and a company's
CNPJ does not change. `assets.cnpj` exists so it is looked up once; this
resolver is what fills it, and `app.domain.fundamentals.identity.
StoredCnpjResolver` is what prefers the stored value over asking again.

## `None` is a real answer

A BDR represents a foreign company, and an ETF or an FII is not a
`companhia aberta` filing a DFP. For those, no CNPJ resolves and none
should be invented — the caller learns the asset has no statements
rather than getting an empty one.
"""

import logging

import httpx

from app.core.config import settings
from app.integrations.fundamentals.exceptions import (
    FundamentalsNotFoundError,
    FundamentalsUnavailableError,
    InvalidFundamentalsResponseError,
)
from app.integrations.http import RetryingJsonClient

logger = logging.getLogger("investment_assistant.fundamentals.identity")


class BrapiCnpjResolver:
    """Reads the CNPJ out of the vendor's company profile module.

    `summaryProfile` is the one module still available on the free plan —
    the statement modules are the ones that left it — so this keeps
    working even while the vendor serves no fundamentals at all.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        token = token if token is not None else settings.BRAPI_TOKEN
        self._http = RetryingJsonClient(
            base_url=base_url or settings.BRAPI_BASE_URL,
            timeout=(
                timeout
                if timeout is not None
                else settings.FUNDAMENTALS_TIMEOUT_SECONDS
            ),
            max_retries=(
                max_retries
                if max_retries is not None
                else settings.FUNDAMENTALS_MAX_RETRIES
            ),
            min_request_interval=settings.FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS,
            not_found_error=FundamentalsNotFoundError,
            unavailable_error=FundamentalsUnavailableError,
            invalid_response_error=InvalidFundamentalsResponseError,
            logger=logger,
            default_params={"token": token} if token else None,
            client=client,
        )

    def close(self) -> None:
        self._http.close()

    def __call__(self, ticker: str) -> str | None:
        try:
            payload = self._http.get_json(
                f"/quote/{ticker}", params={"modules": "summaryProfile"}
            )
        except FundamentalsNotFoundError:
            # The vendor does not know this ticker, which is not the same
            # as the ticker having no CNPJ — but the outcome for the
            # caller is identical, and inventing a distinction would be
            # worse than admitting we cannot tell.
            logger.info("Provider has no profile for %s.", ticker)
            return None

        if not isinstance(payload, dict):
            raise InvalidFundamentalsResponseError(
                f"Profile response for {ticker} was not a JSON object."
            )
        results = payload.get("results") or []
        if not results:
            return None

        profile = results[0].get("summaryProfile") or {}
        cnpj = profile.get("cnpj")
        if not cnpj:
            logger.info("Profile for %s carries no CNPJ.", ticker)
            return None
        return str(cnpj)


class StaticCnpjResolver:
    """A fixed ticker-to-CNPJ mapping.

    For tests, and for a deployment that would rather curate the handful
    of tickers it tracks than spend a request per asset.
    """

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = {key.strip().upper(): value for key, value in mapping.items()}

    def __call__(self, ticker: str) -> str | None:
        return self._mapping.get(ticker.strip().upper())
