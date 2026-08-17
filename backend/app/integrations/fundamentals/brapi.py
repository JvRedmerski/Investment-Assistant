"""`FundamentalsProvider` implementation backed by the Brapi API
(https://brapi.dev), which exposes Yahoo-style financial statement
modules for B3 tickers.

CAVEAT — read before relying on this in production: like
`app.integrations.market_data.brapi`, this parser was written against
Brapi's publicly documented module shape and has been exercised only
against mocked HTTP responses (no outbound network access in this
environment — see docs/PROJECT_STATUS.md). The module names, their
nesting, and the individual field names below are **not confirmed
against a live response**. Smoke-test before real ingestion.

Field mapping (AGENTS.md rule 44 — never invent a figure; a line item
the source does not report stays `None`):

| our field       | source                                              |
|-----------------|-----------------------------------------------------|
| revenue         | incomeStatement.totalRevenue                         |
| net_income      | incomeStatement.netIncome                            |
| equity          | balanceSheet.totalStockholderEquity                  |
| cash            | balanceSheet.cash                                    |
| debt            | balanceSheet.totalDebt, else shortLongTermDebt +     |
|                 | longTermDebt (both are reported liability lines, so  |
|                 | summing them is arithmetic on real data, not an      |
|                 | estimate); `None` if neither is present              |
| ebitda          | always `None` — see below                            |
| free_cash_flow  | always `None` — see below                            |

`ebitda` and `free_cash_flow` are intentionally left unpopulated. Brapi
exposes them only through `financialData`, which is a trailing-twelve-
months snapshot with no period end date. Attaching a TTM figure to a
historical `reference_date` would attribute data to a period it does not
belong to — precisely the look-ahead/point-in-time violation AGENTS.md
rules 108/109 forbid. Deriving them instead (EBITDA from EBIT +
depreciation, FCF from operating cash flow − capex) depends on sign and
labelling conventions that cannot be verified without a live response,
and a silently wrong number is worse than an honest `None`.
"""

import logging
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.exceptions import (
    FundamentalsNotFoundError,
    FundamentalsUnavailableError,
    InvalidFundamentalsResponseError,
)
from app.integrations.fundamentals.schemas import FinancialStatement
from app.integrations.http import RetryingJsonClient

logger = logging.getLogger("investment_assistant.fundamentals.brapi")

_MODULES = "incomeStatementHistory,balanceSheetHistory"


class BrapiFundamentalsProvider(FundamentalsProvider):
    """`FundamentalsProvider` backed by https://brapi.dev/api."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        min_request_interval: float | None = None,
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
            min_request_interval=(
                min_request_interval
                if min_request_interval is not None
                else settings.FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS
            ),
            not_found_error=FundamentalsNotFoundError,
            unavailable_error=FundamentalsUnavailableError,
            invalid_response_error=InvalidFundamentalsResponseError,
            logger=logger,
            default_params={"token": token} if token else None,
            client=client,
        )

    def close(self) -> None:
        self._http.close()

    def get_annual_statements(self, ticker: str) -> list[FinancialStatement]:
        payload = self._http.get_json(f"/quote/{ticker}", params={"modules": _MODULES})
        result = _extract_result(payload, ticker)

        income_by_date = _rows_by_reference_date(
            result, "incomeStatementHistory", ticker
        )
        balance_by_date = _rows_by_reference_date(result, "balanceSheetHistory", ticker)

        if not income_by_date and not balance_by_date:
            raise InvalidFundamentalsResponseError(
                f"Brapi returned no income statement or balance sheet rows "
                f"for {ticker}."
            )

        statements = [
            _build_statement(
                reference_date,
                income_by_date.get(reference_date, {}),
                balance_by_date.get(reference_date, {}),
                ticker,
            )
            for reference_date in sorted(set(income_by_date) | set(balance_by_date))
        ]
        return statements


# -- parsing helpers -------------------------------------------------


def _extract_result(payload: dict[str, Any], ticker: str) -> dict[str, Any]:
    results = payload.get("results")
    if not results:
        raise FundamentalsNotFoundError(
            f"No data returned by Brapi for ticker {ticker}."
        )
    return results[0]


def _rows_by_reference_date(
    result: dict[str, Any], module_key: str, ticker: str
) -> dict[date, dict[str, Any]]:
    """Pull one module's statement rows out, keyed by period end date.

    Brapi wraps a module either as a bare list or as an object containing
    the list under a nested key (the Yahoo-derived shape). Both are
    accepted because the exact nesting could not be verified live; an
    unrecognised shape is reported rather than silently ignored.

    A row without a usable `endDate` is skipped with a warning: it cannot
    be attributed to a reference period, and guessing one would violate
    AGENTS.md rule 109.
    """
    module = result.get(module_key)
    if module is None:
        return {}

    if isinstance(module, dict):
        rows = next(
            (value for value in module.values() if isinstance(value, list)),
            None,
        )
    elif isinstance(module, list):
        rows = module
    else:
        rows = None

    if rows is None:
        raise InvalidFundamentalsResponseError(
            f"Brapi module '{module_key}' for {ticker} has an unrecognised shape: "
            f"{type(module).__name__}."
        )

    by_date: dict[date, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise InvalidFundamentalsResponseError(
                f"Brapi module '{module_key}' for {ticker} contains a non-object row."
            )
        raw_end_date = row.get("endDate")
        if raw_end_date is None:
            logger.warning(
                "Skipping %s row for %s: no endDate to attribute it to.",
                module_key,
                ticker,
            )
            continue
        by_date[_parse_reference_date(raw_end_date, ticker)] = row

    return by_date


def _build_statement(
    reference_date: date,
    income: dict[str, Any],
    balance: dict[str, Any],
    ticker: str,
) -> FinancialStatement:
    try:
        return FinancialStatement(
            reference_date=reference_date,
            revenue=_decimal_or_none(income.get("totalRevenue")),
            ebitda=None,  # not available per period — see module docstring
            net_income=_decimal_or_none(income.get("netIncome")),
            equity=_decimal_or_none(balance.get("totalStockholderEquity")),
            debt=_total_debt(balance),
            cash=_decimal_or_none(balance.get("cash")),
            free_cash_flow=None,  # not available per period — see docstring
        )
    except (InvalidOperation, ValueError) as exc:
        raise InvalidFundamentalsResponseError(
            f"Brapi statement for {ticker} at {reference_date} could not be "
            f"parsed: {exc}"
        ) from exc


def _total_debt(balance: dict[str, Any]) -> Decimal | None:
    total = _decimal_or_none(balance.get("totalDebt"))
    if total is not None:
        return total

    components = [
        _decimal_or_none(balance.get("shortLongTermDebt")),
        _decimal_or_none(balance.get("longTermDebt")),
    ]
    reported = [value for value in components if value is not None]
    if not reported:
        return None
    return sum(reported, Decimal(0))


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise InvalidFundamentalsResponseError(
            f"Value {value!r} is not a valid number."
        ) from exc


def _parse_reference_date(value: Any, ticker: str) -> date:
    if isinstance(value, bool):
        raise InvalidFundamentalsResponseError(
            f"Unrecognized endDate for {ticker}: {value!r}"
        )
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC).date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError as exc:
            raise InvalidFundamentalsResponseError(
                f"Unrecognized endDate for {ticker}: {value!r}"
            ) from exc
    raise InvalidFundamentalsResponseError(
        f"Unrecognized endDate type for {ticker}: {type(value).__name__}"
    )
