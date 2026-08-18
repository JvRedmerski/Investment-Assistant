"""`BenchmarkProvider` backed by the Banco Central do Brasil's SGS API
(https://api.bcb.gov.br/dados/serie), an open, token-free, quota-free
source for the CDI, the IPCA and the Selic.

Chosen over Brapi for these series for two reasons: Brapi does not serve
them at all, and the SGS is the *primary* source — the CDI a fund reports
against is the one the Banco Central publishes, so there is no vendor
interpretation between us and the official figure.

## What a live response actually looks like

Verified against the real API on 2026-08-18, before any mock in the test
suite was written (AGENTS.md rule 19; the Wave 06 lesson recorded in
docs/PROJECT_STATUS.md, where two wrong field names passed 45 green tests
because every mock was built from the same assumption it was meant to
check):

    GET /bcdata.sgs.12/dados?formato=json
        &dataInicial=02/01/2024&dataFinal=31/01/2024

    [{"data":"02/01/2024","valor":"0.043739"}, ...]

Dates are `dd/MM/yyyy`, never ISO. Values are decimal *strings*, and for
a rate series they are **percents** — `0.043739` means 0.043739% for that
day, which this module divides by 100 so the rest of the project only
ever sees fractions (see `schemas`).

Three behaviours of this API are surprising enough that only a live call
would have revealed them, and each is handled below:

1. **HTTP 404 means "no observation in this window"**, not "no such
   series". Asking for the CDI across a weekend returns 404 with
   `SGSNegocioException: Value(s) not found`. Since a sync window may
   legitimately contain no business day, 404 is translated into an empty
   result rather than an error.

2. **An unknown series number returns HTTP 200 with an HTML page**, not a
   JSON error. That fails JSON parsing, so `RetryingJsonClient` raises
   `InvalidBenchmarkResponseError` — the right outcome, reached by an
   unexpected route, and pinned by a test.

3. **A daily series rejects any window wider than 10 calendar years**
   with HTTP 406. The boundary is inclusive-exact: 2016-08-18 to
   2026-08-18 is accepted and one day more is refused. Requests are
   therefore split into narrower windows; see `_windows`.

Resilience (timeout, bounded retry, throttle, HTTP errors — AGENTS.md
rule 22) is delegated to the shared `RetryingJsonClient`, as the two
existing integrations do.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Self

import httpx

from app.core.config import settings
from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.exceptions import (
    BenchmarkSeriesNotFoundError,
    BenchmarkUnavailableError,
    InvalidBenchmarkResponseError,
)
from app.integrations.benchmarks.schemas import BenchmarkKind, BenchmarkObservation
from app.integrations.http import RetryingJsonClient

logger = logging.getLogger("investment_assistant.benchmarks.bcb")

#: Widest window the SGS accepts for a daily series, in whole years.
#:
#: The API's own message states 10 years, and the boundary was probed:
#: dataInicial=18/08/2016 with dataFinal=18/08/2026 returns 200, while
#: 17/08/2016 with the same end returns 406. We chunk one day *inside*
#: the limit rather than exactly on it, so a leap-year edge cannot turn a
#: backfill into a 406. The cost is one extra request per decade against
#: an API with no quota.
MAX_WINDOW_YEARS = 10

#: Percent-to-fraction divisor for `RATE` series.
#:
#: The SGS publishes every rate series in percent. Converting here, at
#: the only point that reads the source, keeps the factor of 100 out of
#: the domain, where it would be invisible: a rate stored as `0.05` is a
#: plausible-looking 5% and a catastrophic 100x error if it meant 0.05%.
PERCENT = Decimal(100)


class BcbSgsProvider(BenchmarkProvider):
    """`BenchmarkProvider` backed by the Banco Central's SGS API."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        min_request_interval: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._http = RetryingJsonClient(
            base_url=base_url or settings.BCB_SGS_BASE_URL,
            timeout=(
                timeout if timeout is not None else settings.BENCHMARK_TIMEOUT_SECONDS
            ),
            max_retries=(
                max_retries
                if max_retries is not None
                else settings.BENCHMARK_MAX_RETRIES
            ),
            min_request_interval=(
                min_request_interval
                if min_request_interval is not None
                else settings.BENCHMARK_MIN_REQUEST_INTERVAL_SECONDS
            ),
            not_found_error=BenchmarkSeriesNotFoundError,
            unavailable_error=BenchmarkUnavailableError,
            invalid_response_error=InvalidBenchmarkResponseError,
            logger=logger,
            default_params={"formato": "json"},
            client=client,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_series(
        self,
        series_id: str,
        start: date,
        end: date,
        kind: BenchmarkKind,
    ) -> list[BenchmarkObservation]:
        if start > end:
            raise ValueError("start date must not be after end date")

        observations: list[BenchmarkObservation] = []
        for window_start, window_end in _windows(start, end):
            observations.extend(
                self._fetch_window(series_id, window_start, window_end, kind)
            )

        # The SGS returns each window ordered, and the windows themselves
        # are generated in order, but sorting is cheap insurance against
        # relying on an ordering the source never promised.
        observations.sort(key=lambda observation: observation.date)
        return observations

    # -- internals ---------------------------------------------------

    def _fetch_window(
        self,
        series_id: str,
        start: date,
        end: date,
        kind: BenchmarkKind,
    ) -> list[BenchmarkObservation]:
        params = {
            "dataInicial": _format_date(start),
            "dataFinal": _format_date(end),
        }
        try:
            payload = self._http.get_json(f"/bcdata.sgs.{series_id}/dados", params)
        except BenchmarkSeriesNotFoundError:
            # See the module docstring, point 1: the SGS answers 404 for a
            # window that simply holds no observation. Raising here would
            # make a sync fail every time it happened to cover only a
            # weekend or a holiday.
            logger.info(
                "SGS series %s has no observation between %s and %s.",
                series_id,
                start,
                end,
            )
            return []

        if not isinstance(payload, list):
            raise InvalidBenchmarkResponseError(
                f"SGS series {series_id} returned {type(payload).__name__}, "
                f"expected a JSON array."
            )
        return [self._parse_observation(raw, series_id, kind) for raw in payload]

    @staticmethod
    def _parse_observation(
        raw: Any, series_id: str, kind: BenchmarkKind
    ) -> BenchmarkObservation:
        if not isinstance(raw, dict):
            raise InvalidBenchmarkResponseError(
                f"SGS series {series_id} returned a non-object entry: {raw!r}"
            )

        raw_date = raw.get("data")
        if raw_date is None:
            raise InvalidBenchmarkResponseError(
                f"SGS series {series_id} returned an entry with no date: {raw!r}"
            )

        raw_value = raw.get("valor")
        # The SGS uses an empty string for a date it lists without a
        # figure. Passed through as `None` rather than dropped or
        # defaulted, so the quality report can account for it (ADR-016).
        value: Decimal | None = None
        if raw_value is not None and str(raw_value).strip() != "":
            try:
                value = Decimal(str(raw_value).strip())
            except InvalidOperation as exc:
                raise InvalidBenchmarkResponseError(
                    f"SGS series {series_id} returned an unparseable value "
                    f"{raw_value!r} for {raw_date}."
                ) from exc
            if kind is BenchmarkKind.RATE:
                value = value / PERCENT

        return BenchmarkObservation(date=_parse_date(raw_date, series_id), value=value)


def _format_date(day: date) -> str:
    """The SGS accepts `dd/MM/yyyy` only — an ISO date is rejected."""
    return day.strftime("%d/%m/%Y")


def _parse_date(raw: Any, series_id: str) -> date:
    if not isinstance(raw, str):
        raise InvalidBenchmarkResponseError(
            f"SGS series {series_id} returned a non-string date: {raw!r}"
        )
    try:
        day, month, year = (int(part) for part in raw.split("/"))
        return date(year, month, day)
    except ValueError as exc:
        raise InvalidBenchmarkResponseError(
            f"SGS series {series_id} returned an unrecognized date: {raw!r}"
        ) from exc


def _windows(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] into windows the SGS will accept.

    Each window spans just under `MAX_WINDOW_YEARS` calendar years, so a
    multi-decade backfill becomes several requests instead of one HTTP
    406. Windows are contiguous and non-overlapping, so no observation is
    fetched twice or missed at a seam.
    """
    windows: list[tuple[date, date]] = []
    window_start = start
    while window_start <= end:
        limit = _add_years(window_start, MAX_WINDOW_YEARS) - timedelta(days=1)
        window_end = min(end, limit)
        windows.append((window_start, window_end))
        window_start = window_end + timedelta(days=1)
    return windows


def _add_years(day: date, years: int) -> date:
    """`day` shifted by whole calendar years, clamping 29 February.

    `date.replace(year=...)` raises on 29 February when the target year is
    not a leap year, which would make a backfill starting on a leap day
    crash rather than chunk.
    """
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)
