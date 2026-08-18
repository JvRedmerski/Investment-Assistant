"""`FundamentalsProvider` implementation backed by the Brapi API
(https://brapi.dev), which exposes Yahoo-style financial statement
modules for B3 tickers.

VERIFIED against a live response on 2026-08-17 (W06-003), using a single
`GET /quote/PETR4` with 16 annual periods. The mapping below reflects
what the API actually returns, not what its documentation implies — the
first version of this parser was written from the docs alone and got two
fields wrong (see "Corrections" at the end).

Field mapping (AGENTS.md rule 44 — never invent a figure; a line item
the source does not report stays `None`):

| our field          | source                                            |
|--------------------|---------------------------------------------------|
| revenue            | income.totalRevenue                    (16/16)    |
| net_income         | income.netIncome                       (16/16)    |
| ebit               | income.ebit                            (16/16)    |
| income_before_tax  | income.incomeBeforeTax                 (16/16)    |
| income_tax_expense | income.incomeTaxExpense                (16/16)    |
| cash               | balance.cash                           (16/16)    |
| equity             | balance.shareholdersEquity             (16/16)    |
| debt               | sum of the six reported financial-debt and lease  |
|                    | lines (each 16/16), see `_DEBT_COMPONENTS`        |
| ebitda             | always `None` — see below                         |
| free_cash_flow     | always `None` — see below                         |

Only rows with `type == "yearly"` are returned; the module carries a
`type` discriminator and quarterly rows must not be mixed in (ADR-013).

`ebitda` stays `None` on evidence, not assumption. Brapi exposes a
`cleanEbitda` field on every period, but it is **identical to `ebit` in
all 16 periods** — no depreciation or amortisation is added back, so it
is not EBITDA. Storing it as such would put a silently wrong number
behind `debt_ebitda` and `ebitda_margin`, which is worse than an honest
gap (rule 44).

`free_cash_flow` stays `None`: the cash flow statement module was not
requested, and deriving FCF from operating cash flow − capex depends on
a sign convention not yet verified.

Deliberately **not** used, though present in the response:
- `cleanNopat` — applies a flat 34% tax rate to every period, while the
  actual effective rates for PETR4 range from 26.6% to 32.4%. ROIC is
  instead derived from the reported tax figures (ADR-014: never assume a
  rate).
- `defaultKeyStatistics.sharesOutstanding` / `dividendYield` /
  `marketCap` — current snapshots with no period end date. Applying
  today's share count to a 2010 statement would attribute present-day
  facts to a past period (rules 108/109), so `pe`, `pb` and `dy` remain
  uncomputable pending a per-period source.

## Corrections to the pre-verification mapping

- `equity` read `totalStockholderEquity`, which is **null in all 16
  periods**. The populated field is `shareholdersEquity`.
- `debt` read `totalDebt` (not a key at all) with a fallback to
  `shortLongTermDebt` + `longTermDebt`, **both null in all 16 periods**.

Both bugs made their indicators silently `None` on real data — including
`roe`, which needs equity.
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

#: Only annual periods are ingested (ADR-013).
_ANNUAL_ROW_TYPE = "yearly"

#: Equity, in order of preference. `shareholdersEquity` is the field the
#: live response populates; the other two are the documented names, kept
#: as fallbacks in case another ticker or API version uses them.
_EQUITY_FIELDS = (
    "shareholdersEquity",
    "totalStockholderEquity",
    "controllerShareholdersEquity",
)

#: Gross financial debt, summed from the individual reported lines.
#: Summing reported liability lines is arithmetic on real data, not an
#: estimate. Leases are included: they are contractual debt-like
#: obligations under IFRS 16 and excluding them would understate
#: leverage for a capital-intensive company.
_DEBT_COMPONENTS = (
    "loansAndFinancing",
    "longTermLoansAndFinancing",
    "debentures",
    "longTermDebentures",
    "leaseFinancing",
    "longTermLeaseFinancing",
)

#: Aggregate debt fields, tried before falling back to the components.
_DEBT_TOTAL_FIELDS = ("totalDebt",)


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

    The live response returns a bare list; an object wrapping the list
    under a nested key (the Yahoo-derived shape the docs suggest) is also
    accepted, since other tickers or a future version may use it. An
    unrecognised shape is reported rather than silently ignored.

    Rows whose `type` is not `yearly` are dropped: the `fundamentals`
    table keys on `(asset_id, reference_date)` and cannot distinguish a
    fiscal year from a quarter sharing that end date (ADR-013).

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
        row_type = row.get("type")
        if row_type is not None and row_type != _ANNUAL_ROW_TYPE:
            continue

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
            # `cleanEbitda` is identical to `ebit` in every period the
            # live response returns, so it is not EBITDA — see docstring.
            ebitda=None,
            net_income=_decimal_or_none(income.get("netIncome")),
            equity=_first_reported(balance, _EQUITY_FIELDS),
            debt=_total_debt(balance),
            cash=_decimal_or_none(balance.get("cash")),
            free_cash_flow=None,  # cash flow module not requested
            ebit=_decimal_or_none(income.get("ebit")),
            income_before_tax=_decimal_or_none(income.get("incomeBeforeTax")),
            income_tax_expense=_decimal_or_none(income.get("incomeTaxExpense")),
        )
    except (InvalidOperation, ValueError) as exc:
        raise InvalidFundamentalsResponseError(
            f"Brapi statement for {ticker} at {reference_date} could not be "
            f"parsed: {exc}"
        ) from exc


def _first_reported(
    row: dict[str, Any], field_names: tuple[str, ...]
) -> Decimal | None:
    """The first of `field_names` the source actually reports."""
    for name in field_names:
        value = _decimal_or_none(row.get(name))
        if value is not None:
            return value
    return None


def _total_debt(balance: dict[str, Any]) -> Decimal | None:
    """Gross financial debt for the period.

    Prefers an aggregate field if the source provides one; otherwise sums
    the individual reported debt and lease lines. Returns `None` when the
    source reports none of them, rather than a misleading zero.
    """
    total = _first_reported(balance, _DEBT_TOTAL_FIELDS)
    if total is not None:
        return total

    reported = [
        value
        for name in _DEBT_COMPONENTS
        if (value := _decimal_or_none(balance.get(name))) is not None
    ]
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
