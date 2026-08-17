"""`MarketDataProvider` implementation backed by the Brapi API
(https://brapi.dev), a free B3 market data source.

CAVEAT — read before relying on this in production: this parser was
written against Brapi's publicly documented response shape
(`results[0].regularMarketPrice`, `results[0].historicalDataPrice[]`,
etc.). It has been exercised only against mocked HTTP responses in this
environment (no outbound network access here — see
docs/PROJECT_STATUS.md, Wave 05 technical decisions). It must be smoke-
tested against a live response before being relied on for real ingestion,
exactly like the `002_numeric_money_columns` migration was flagged as
"authored and structurally validated, but not yet verified live."

Resilience choices (AGENTS.md rule 22 — every external integration must
consider timeout/retry/rate limit/HTTP errors/invalid or incomplete
responses/unavailability, and retries must never be infinite):

- bounded retries with exponential backoff, only for transient failures
  (timeouts, connection errors, HTTP 429/500/502/503/504);
- a 404 (ticker not found) or any other 4xx fails immediately, since
  retrying will not change the outcome;
- an optional minimum delay between requests (`MARKET_DATA_MIN_REQUEST_
  INTERVAL_SECONDS`) throttles our own call rate to respect the
  provider's free-tier limits.
"""

import logging
import time
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Self

import httpx

from app.core.config import settings
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import DailyBar, Quote

logger = logging.getLogger("investment_assistant.market_data.brapi")

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class BrapiProvider(MarketDataProvider):
    """`MarketDataProvider` backed by https://brapi.dev/api."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        min_request_interval: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = (base_url or settings.BRAPI_BASE_URL).rstrip("/")
        self._token = token if token is not None else settings.BRAPI_TOKEN
        self._timeout = (
            timeout if timeout is not None else settings.MARKET_DATA_TIMEOUT_SECONDS
        )
        self._max_retries = (
            max_retries if max_retries is not None else settings.MARKET_DATA_MAX_RETRIES
        )
        self._min_request_interval = (
            min_request_interval
            if min_request_interval is not None
            else settings.MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
        )
        self._last_request_at: float | None = None
        # A caller-supplied client makes this provider trivially testable
        # (httpx.Client(transport=httpx.MockTransport(...))) without any
        # real network access.
        self._client = client or httpx.Client(timeout=self._timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_quote(self, ticker: str) -> Quote:
        payload = self._request(f"/quote/{ticker}")
        result = self._extract_result(payload, ticker)
        return self._parse_quote(result, ticker)

    def get_daily_history(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        if start > end:
            raise ValueError("start date must not be after end date")

        params = {"range": _brapi_range_for(start, end), "interval": "1d"}
        payload = self._request(f"/quote/{ticker}", params=params)
        result = self._extract_result(payload, ticker)

        raw_bars = result.get("historicalDataPrice")
        if raw_bars is None:
            raise InvalidMarketDataResponseError(
                f"Brapi response for {ticker} has no 'historicalDataPrice'."
            )

        bars = [self._parse_bar(raw, ticker) for raw in raw_bars]
        return [bar for bar in bars if start <= bar.date <= end]

    # -- internals ---------------------------------------------------

    def _throttle(self) -> None:
        if self._min_request_interval <= 0 or self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self._min_request_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _request(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        query = dict(params or {})
        if self._token:
            query["token"] = self._token

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            self._last_request_at = time.monotonic()
            try:
                response = self._client.get(f"{self._base_url}{path}", params=query)
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "Brapi request timed out (attempt %s/%s): %s",
                    attempt,
                    self._max_retries,
                    path,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "Brapi request failed (attempt %s/%s): %s: %s",
                    attempt,
                    self._max_retries,
                    path,
                    exc,
                )
            else:
                if response.status_code == 404:
                    raise TickerNotFoundError(f"Ticker not found: {path}")
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = MarketDataUnavailableError(
                        f"Brapi returned HTTP {response.status_code} for {path}"
                    )
                    logger.warning(
                        "Brapi returned retryable status %s (attempt %s/%s): %s",
                        response.status_code,
                        attempt,
                        self._max_retries,
                        path,
                    )
                elif response.status_code >= 400:
                    raise MarketDataUnavailableError(
                        f"Brapi returned HTTP {response.status_code} for {path}: "
                        f"{response.text[:200]}"
                    )
                else:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise InvalidMarketDataResponseError(
                            f"Brapi response for {path} was not valid JSON."
                        ) from exc

            if attempt < self._max_retries:
                time.sleep(_backoff_seconds(attempt))

        raise MarketDataUnavailableError(
            f"Brapi request to {path} failed after {self._max_retries} attempt(s)."
        ) from last_error

    @staticmethod
    def _extract_result(payload: dict[str, Any], ticker: str) -> dict[str, Any]:
        results = payload.get("results")
        if not results:
            raise TickerNotFoundError(f"No data returned by Brapi for ticker {ticker}.")
        return results[0]

    @staticmethod
    def _parse_quote(result: dict[str, Any], ticker: str) -> Quote:
        try:
            price = result["regularMarketPrice"]
            as_of_raw = result["regularMarketTime"]
        except KeyError as exc:
            raise InvalidMarketDataResponseError(
                f"Brapi quote for {ticker} is missing field {exc}."
            ) from exc

        if price is None:
            raise InvalidMarketDataResponseError(
                f"Brapi quote for {ticker} has a null price."
            )

        currency = result.get("currency") or "BRL"
        try:
            return Quote(
                ticker=ticker,
                price=Decimal(str(price)),
                currency=currency,
                as_of=_parse_timestamp(as_of_raw),
            )
        except (InvalidOperation, ValueError) as exc:
            raise InvalidMarketDataResponseError(
                f"Brapi quote for {ticker} could not be parsed: {exc}"
            ) from exc

    @staticmethod
    def _parse_bar(raw: dict[str, Any], ticker: str) -> DailyBar:
        required = ("date", "open", "high", "low", "close", "volume")
        missing = [field for field in required if raw.get(field) is None]
        if missing:
            raise InvalidMarketDataResponseError(
                f"Brapi daily bar for {ticker} is missing field(s): {', '.join(missing)}."
            )
        try:
            bar_date = _parse_timestamp(raw["date"]).date()
            adjusted_close = raw.get("adjustedClose")
            if adjusted_close is None:
                adjusted_close = raw["close"]
            return DailyBar(
                date=bar_date,
                open=Decimal(str(raw["open"])),
                high=Decimal(str(raw["high"])),
                low=Decimal(str(raw["low"])),
                close=Decimal(str(raw["close"])),
                adjusted_close=Decimal(str(adjusted_close)),
                volume=Decimal(str(raw["volume"])),
            )
        except (InvalidOperation, ValueError) as exc:
            raise InvalidMarketDataResponseError(
                f"Brapi daily bar for {ticker} could not be parsed: {exc}"
            ) from exc


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, bool):
        raise InvalidMarketDataResponseError(f"Unrecognized timestamp value: {value!r}")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise InvalidMarketDataResponseError(
                f"Unrecognized timestamp: {value!r}"
            ) from exc
    raise InvalidMarketDataResponseError(
        f"Unrecognized timestamp type: {type(value)!r}"
    )


def _backoff_seconds(attempt: int) -> float:
    return min(2 ** (attempt - 1) * 0.5, 5.0)


def _brapi_range_for(start: date, end: date) -> str:
    """Pick the smallest Brapi `range` bucket that covers [start, end].

    Brapi only accepts a fixed set of range buckets (not arbitrary date
    spans); we request the smallest bucket that covers the requested
    window and filter precisely by date afterwards.
    """
    days = (end - start).days
    if days <= 5:
        return "5d"
    if days <= 30:
        return "1mo"
    if days <= 90:
        return "3mo"
    if days <= 180:
        return "6mo"
    if days <= 365:
        return "1y"
    if days <= 365 * 2:
        return "2y"
    if days <= 365 * 5:
        return "5y"
    return "max"
