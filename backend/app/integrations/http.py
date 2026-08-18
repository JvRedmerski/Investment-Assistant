"""Shared HTTP transport for outbound provider integrations.

Every external provider in this project needs the same resilience
behaviour (AGENTS.md rule 22 — timeout, retry, rate limit, HTTP errors,
invalid/incomplete responses, unavailability, and never an infinite
retry):

- bounded retries with exponential backoff, only for transient failures
  (timeouts, connection errors, HTTP 429/500/502/503/504);
- immediate failure for anything retrying cannot fix (404 and other 4xx);
- an optional minimum delay between requests, throttling our own call
  rate to respect a provider's free-tier limits.

Rather than each provider carrying its own copy of that loop (AGENTS.md
rule 8 — do not reimplement what already exists), they share this class
and supply their own domain-specific exception types, so callers of
`market_data` still see `MarketDataUnavailableError` and callers of
`fundamentals` see `FundamentalsUnavailableError`.
"""

import logging
import time
from typing import Any, Self

import httpx

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class RetryingJsonClient:
    """A small `httpx` wrapper that returns parsed JSON or raises a
    provider-specific exception.

    The exception *classes* are injected so this stays domain-agnostic:
    each integration package keeps its own error vocabulary.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        max_retries: int,
        min_request_interval: float,
        not_found_error: type[Exception],
        unavailable_error: type[Exception],
        invalid_response_error: type[Exception],
        logger: logging.Logger,
        default_params: dict[str, Any] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._min_request_interval = min_request_interval
        self._not_found_error = not_found_error
        self._unavailable_error = unavailable_error
        self._invalid_response_error = invalid_response_error
        self._logger = logger
        self._default_params = dict(default_params or {})
        self._last_request_at: float | None = None
        # A caller-supplied client makes every provider trivially testable
        # (httpx.Client(transport=httpx.MockTransport(...))) without any
        # real network access.
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """The parsed JSON document at `path`.

        Typed `Any` rather than `dict` because a JSON document is not
        always an object: Brapi returns one, while the Banco Central's
        SGS returns a bare array. Each provider narrows the shape it
        expects and raises its own invalid-response error otherwise -
        which is where that check belongs, since only the provider knows
        what its source promises.
        """
        query = {**self._default_params, **(params or {})}

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            self._last_request_at = time.monotonic()
            try:
                response = self._client.get(f"{self._base_url}{path}", params=query)
            except httpx.TimeoutException as exc:
                last_error = exc
                self._logger.warning(
                    "Request timed out (attempt %s/%s): %s",
                    attempt,
                    self._max_retries,
                    path,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                self._logger.warning(
                    "Request failed (attempt %s/%s): %s: %s",
                    attempt,
                    self._max_retries,
                    path,
                    exc,
                )
            else:
                if response.status_code == 404:
                    raise self._not_found_error(f"Not found: {path}")
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = self._unavailable_error(
                        f"Provider returned HTTP {response.status_code} for {path}"
                    )
                    self._logger.warning(
                        "Provider returned retryable status %s (attempt %s/%s): %s",
                        response.status_code,
                        attempt,
                        self._max_retries,
                        path,
                    )
                elif response.status_code >= 400:
                    raise self._unavailable_error(
                        f"Provider returned HTTP {response.status_code} for {path}: "
                        f"{response.text[:200]}"
                    )
                else:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise self._invalid_response_error(
                            f"Provider response for {path} was not valid JSON."
                        ) from exc

            if attempt < self._max_retries:
                time.sleep(backoff_seconds(attempt))

        raise self._unavailable_error(
            f"Request to {path} failed after {self._max_retries} attempt(s)."
        ) from last_error

    def _throttle(self) -> None:
        if self._min_request_interval <= 0 or self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self._min_request_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)


def backoff_seconds(attempt: int) -> float:
    return min(2 ** (attempt - 1) * 0.5, 5.0)
