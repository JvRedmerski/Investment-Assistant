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

Resilience (AGENTS.md rule 22 — timeout, bounded retry, rate limit, HTTP
errors, invalid responses, unavailability) is delegated to the shared
`app.integrations.http.RetryingJsonClient`, configured here with this
integration's own exception types and with
`MARKET_DATA_TIMEOUT_SECONDS` / `MARKET_DATA_MAX_RETRIES` /
`MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS`. This module is therefore
only responsible for Brapi's URL shape and response parsing.
"""

import logging
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Self

import httpx

from app.core.config import settings
from app.integrations.http import RetryingJsonClient
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.exceptions import (
    HistoryWindowTooLargeError,
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import DailyBar, Quote

logger = logging.getLogger("investment_assistant.market_data.brapi")


class BrapiProvider(MarketDataProvider):
    """`MarketDataProvider` backed by https://brapi.dev/api."""

    source_name = "brapi"

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        min_request_interval: float | None = None,
        max_range: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        token = token if token is not None else settings.BRAPI_TOKEN
        self._max_range = (
            max_range if max_range is not None else settings.BRAPI_MAX_RANGE
        )
        self._http = RetryingJsonClient(
            base_url=base_url or settings.BRAPI_BASE_URL,
            timeout=(
                timeout if timeout is not None else settings.MARKET_DATA_TIMEOUT_SECONDS
            ),
            max_retries=(
                max_retries
                if max_retries is not None
                else settings.MARKET_DATA_MAX_RETRIES
            ),
            min_request_interval=(
                min_request_interval
                if min_request_interval is not None
                else settings.MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
            ),
            not_found_error=TickerNotFoundError,
            unavailable_error=MarketDataUnavailableError,
            invalid_response_error=InvalidMarketDataResponseError,
            logger=logger,
            default_params={"token": token} if token else None,
            client=client,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_quote(self, ticker: str) -> Quote:
        payload = self._http.get_json(f"/quote/{ticker}")
        result = self._extract_result(payload, ticker)
        return self._parse_quote(result, ticker)

    def get_daily_history(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        if start > end:
            raise ValueError("start date must not be after end date")

        today = datetime.now(UTC).date()
        params = {
            "range": _brapi_range_for(start, today, self._max_range),
            "interval": "1d",
        }
        payload = self._http.get_json(f"/quote/{ticker}", params=params)
        result = self._extract_result(payload, ticker)

        raw_bars = result.get("historicalDataPrice")
        if raw_bars is None:
            raise InvalidMarketDataResponseError(
                f"Brapi response for {ticker} has no 'historicalDataPrice'."
            )

        bars = [self._parse_bar(raw, ticker) for raw in raw_bars]
        return [bar for bar in bars if start <= bar.date <= end]

    # -- internals ---------------------------------------------------

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
            # Passed through as reported, `None` included. Brapi leaves
            # `adjustedClose` null on the most recently closed session and
            # backfills it later (verified 2026-08-18: null for 2026-08-17
            # on HGLG11, BOVA11 and ITUB4 alike). Defaulting it to `close`
            # would fabricate an adjustment that does not exist, and since
            # `sync_daily_history` never rewrites a stored date, that wrong
            # value would be frozen in permanently. `validate_daily_bars`
            # rejects the bar instead, so a later sync stores it once the
            # source publishes the real figure.
            adjusted_close = raw.get("adjustedClose")
            return DailyBar(
                date=bar_date,
                open=Decimal(str(raw["open"])),
                high=Decimal(str(raw["high"])),
                low=Decimal(str(raw["low"])),
                close=Decimal(str(raw["close"])),
                adjusted_close=(
                    Decimal(str(adjusted_close)) if adjusted_close is not None else None
                ),
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


#: Brapi's range buckets, smallest first, with the number of days back from
#: today each one reaches. There is no start-date parameter: every bucket is
#: anchored at today, which is why reaching `start` - not spanning
#: [start, end] - is what decides the bucket.
_BRAPI_RANGES: tuple[tuple[str, int], ...] = (
    ("1d", 1),
    ("5d", 5),
    ("1mo", 30),
    ("3mo", 90),
    ("6mo", 180),
    ("1y", 365),
    ("2y", 365 * 2),
    ("5y", 365 * 5),
    ("max", 365 * 100),
)


def _brapi_range_for(start: date, today: date, max_range: str) -> str:
    """Pick the smallest Brapi `range` bucket that reaches back to `start`.

    Brapi accepts a fixed set of range buckets rather than arbitrary date
    spans, and **every bucket ends at today** - the API takes no start
    date. So the bucket has to cover `today - start`, not `end - start`:
    sizing it from the requested window alone made any query about the past
    return bars that the caller then filtered away to nothing. Asking for
    two weeks of last quarter used to send `range=5d`, which cannot contain
    a single bar of the window requested.

    `max_range` caps the bucket at what the account's plan actually serves
    (`BRAPI_MAX_RANGE`, `3mo` on the free plan). Beyond it the API answers
    HTTP 400 `INVALID_RANGE`, so this raises `HistoryWindowTooLargeError`
    rather than spending a request to be told no.
    """
    known = [name for name, _ in _BRAPI_RANGES]
    if max_range not in known:
        raise ValueError(
            f"BRAPI_MAX_RANGE must be one of {', '.join(known)}; got {max_range!r}."
        )

    days_back = (today - start).days
    cap_index = known.index(max_range)

    for index, (name, reach) in enumerate(_BRAPI_RANGES):
        if days_back <= reach:
            if index > cap_index:
                break
            return name

    raise HistoryWindowTooLargeError(
        f"History from {start.isoformat()} needs {days_back} days of range, "
        f"beyond the '{max_range}' cap this plan serves. Brapi anchors every "
        f"range at today and accepts no start date, so the window cannot be "
        f"paginated. Raise BRAPI_MAX_RANGE if the account's plan allows more."
    )
