"""`FundamentalsProvider` backed by the CVM's open data portal.

https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/

This is the **primary source**: the DFP is the filing itself, as
delivered to the regulator, not a vendor's reading of it. It is free, has
no token and no quota, and it goes back well over a decade — which is
exactly what the configured commercial source stopped providing when its
statement modules left the free plan (docs/PROJECT_STATUS.md).

It is also a completely different shape of API, and every difference
below was verified against the real files on 2026-08-18 before any mock
in the test suite was written.

## What the source actually is

Not a REST API. One ZIP per fiscal year (~13 MB), holding one CSV per
statement type, each containing **every listed company**. There is no way
to ask for a single company, so the year file is downloaded once and
cached; see `CvmArchive`.

The CSVs are `;`-separated, **latin-1** encoded, with a `.` decimal
separator, and identify a company by **CNPJ** — never by ticker. Bridging
that gap is what `CnpjResolver` is for, and it is the point at which this
integration and the market data vendor are merged: the vendor knows what
`PETR4` is, and the CVM knows what `33.000.167/0001-01` reported.

## Four columns that change the answer

- **`ESCALA_MOEDA`** is `MIL` for most filings and `UNIDADE` for some
  (550 of 32,776 rows in the 2024 income statements). Ignoring it
  understates a company by a factor of a thousand.
- **`ORDEM_EXERC`** is `ÚLTIMO` or `PENÚLTIMO`: every file carries the
  prior year as a comparative. Only `ÚLTIMO` is read, because the
  comparative figure is the *restated* view from a later filing, and the
  prior year's own file already holds it as filed.
- **`VERSAO`** increments when a filing is re-delivered. The highest
  version for a period wins, which is the one correction the source makes
  available and that the vendor never exposed at all.
- **`ORDEM_EXERC` plus `DT_FIM_EXERC`** give the period end, which is the
  `reference_date` the record is stored under (rule 109).

## Consolidated, not individual

Only the `_con_` files are read. The `_ind_` ones report the parent
company alone, so a holding company would show almost no revenue. An
investor buying the share owns the group.

## The account codes, and how each was checked

`CD_CONTA` is a structured code that is standard across filers. Verified
against PETR4's 2024 DFP, whose published figures are public:

| field | code | PETR4 2024 |
|---|---|---|
| `revenue` | `3.01` | R$ 490.8 bn |
| `ebit` | `3.05` | R$ 137.2 bn |
| `income_before_tax` | `3.07` | R$ 54.7 bn |
| `income_tax_expense` | `3.08` | R$ -17.7 bn |
| `net_income` | `3.11.01` | R$ 36.6 bn |
| `equity` | `2.03` less `2.03.09` | R$ 366.0 bn |
| `debt` | `2.01.04` + `2.02.01` | R$ 373.5 bn |
| `cash` | `1.01.01` | R$ 20.3 bn |

**`net_income` is `3.11.01`, not `3.11`.** The latter is the consolidated
result including non-controlling interests (R$ 37.0 bn for PETR4), and
pairing it with equity attributable to the parent would inflate ROE by
the minority's share. Equity is netted the same way for the same reason,
so numerator and denominator describe the same owners.

## EBITDA is derived, and says so

The CVM does not report EBITDA — no filing does, because it is not an
accounting standard. It is derived here as `EBIT + |D&A|`, with D&A taken
from the value-added statement at `7.04.01`, present for 450 of the 467
companies in the 2024 file. For PETR4 that gives R$ 204.2 bn, matching
the figure the company reports.

The absolute value is deliberate: the DVA presents retentions as
deductions, so D&A arrives negative for 433 companies, zero for 16 and
positive for 3. The sign is a presentation convention; the magnitude is
the quantity. Where `7.04.01` is absent, `ebitda` stays `None`.

This is **not** a company's "adjusted EBITDA", which excludes whatever
that company chose to call non-recurring. It is the unadjusted
arithmetic, identical across every filer, which is what makes it
comparable.

## Free cash flow is not derived

The cash flow statement gives net investing activity (`6.02`), not
capital expenditure, and the two differ by acquisitions and financial
investments. Splitting capex out needs a sub-account whose code varies by
filer, so `free_cash_flow` stays `None` rather than being approximated
(rule 44). No indicator currently consumes it.
"""

import csv
import io
import logging
import time
import zipfile
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from app.core.config import settings
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.exceptions import (
    FundamentalsNotFoundError,
    FundamentalsUnavailableError,
    InvalidFundamentalsResponseError,
)
from app.integrations.fundamentals.schemas import FinancialStatement
from app.integrations.http import backoff_seconds

logger = logging.getLogger("investment_assistant.fundamentals.cvm")

#: Resolves a B3 ticker to the CNPJ the CVM files it under.
#:
#: Injected rather than implemented here, because the two halves come
#: from different worlds: the CVM has no idea what a ticker is, and the
#: market data vendor does. Returning `None` means "this ticker has no
#: CVM filer", which is the honest answer for a BDR or an offshore ETF.
CnpjResolver = Callable[[str], str | None]

#: How the CVM writes an amount's scale, and what to multiply by.
SCALE_MULTIPLIERS: dict[str, Decimal] = {
    "MIL": Decimal(1000),
    "UNIDADE": Decimal(1),
}

#: Only the most recent fiscal year in each file is read; see the
#: module docstring on `ORDEM_EXERC`.
CURRENT_PERIOD = "ÚLTIMO"

#: Statement CSVs read out of a year's archive, by the prefix they carry.
BALANCE_ASSETS = "BPA_con"
BALANCE_LIABILITIES = "BPP_con"
INCOME = "DRE_con"
VALUE_ADDED = "DVA_con"

#: `CD_CONTA` codes, one per figure. See the table in the module
#: docstring for how each was verified.
REVENUE = "3.01"
EBIT = "3.05"
INCOME_BEFORE_TAX = "3.07"
INCOME_TAX = "3.08"
NET_INCOME_OWNERS = "3.11.01"
NET_INCOME_CONSOLIDATED = "3.11"
EQUITY_TOTAL = "2.03"
EQUITY_MINORITY = "2.03.09"
DEBT_CURRENT = "2.01.04"
DEBT_NON_CURRENT = "2.02.01"
CASH = "1.01.01"
DEPRECIATION = "7.04.01"


class CvmArchive:
    """Downloads and caches one DFP year archive.

    The unit of retrieval is a whole year for every listed company, so
    caching is not an optimisation — it is what makes per-ticker access
    possible at all. Without it, scoring twenty assets would download the
    same 13 MB twenty times.

    A cached file is never re-downloaded, which means a year already on
    disk is frozen as it was fetched. The CVM does re-publish a year as
    companies file corrections, so picking those up means deleting the
    cached archive — a deliberate act, never something a read path
    triggers on its own.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir or settings.CVM_CACHE_DIR)
        self._base_url = (base_url or settings.CVM_DFP_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.CVM_TIMEOUT_SECONDS
        self._max_retries = (
            max_retries if max_retries is not None else settings.CVM_MAX_RETRIES
        )
        self._client = client or httpx.Client(timeout=self._timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def path_for(self, year: int) -> Path:
        return self._cache_dir / f"dfp_cia_aberta_{year}.zip"

    def fetch(self, year: int) -> Path | None:
        """The local archive for `year`, downloading it if absent.

        `None` when the CVM has no file for that year — which is the
        normal answer for a year whose filings are not out yet, not an
        error.
        """
        cached = self.path_for(year)
        if cached.exists():
            return cached

        url = f"{self._base_url}/dfp_cia_aberta_{year}.zip"
        payload = self._download(url, year)
        if payload is None:
            return None

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # Written via a temporary name and moved into place, so an
        # interrupted download can never leave a truncated archive that
        # every later run would treat as cached.
        staging = cached.with_suffix(".partial")
        staging.write_bytes(payload)
        staging.replace(cached)
        return cached

    def _download(self, url: str, year: int) -> bytes | None:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.get(url, follow_redirects=True)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "CVM download failed (attempt %s/%s) for %s: %s",
                    attempt,
                    self._max_retries,
                    year,
                    exc,
                )
            else:
                if response.status_code == 404:
                    logger.info("CVM has no DFP archive for %s.", year)
                    return None
                if response.status_code < 400:
                    return response.content
                last_error = FundamentalsUnavailableError(
                    f"CVM returned HTTP {response.status_code} for {year}."
                )
                logger.warning(
                    "CVM returned HTTP %s (attempt %s/%s) for %s.",
                    response.status_code,
                    attempt,
                    self._max_retries,
                    year,
                )
            if attempt < self._max_retries:
                time.sleep(backoff_seconds(attempt))

        raise FundamentalsUnavailableError(
            f"CVM archive for {year} could not be downloaded."
        ) from last_error


class CvmFundamentalsProvider(FundamentalsProvider):
    """Annual statements read from the CVM's DFP archives."""

    def __init__(
        self,
        resolve_cnpj: CnpjResolver,
        archive: CvmArchive | None = None,
        first_year: int | None = None,
        last_year: int | None = None,
    ) -> None:
        self._resolve_cnpj = resolve_cnpj
        self._archive = archive or CvmArchive()
        self._first_year = (
            first_year if first_year is not None else settings.CVM_FIRST_YEAR
        )
        self._last_year = last_year

    def close(self) -> None:
        self._archive.close()

    def get_annual_statements(self, ticker: str) -> list[FinancialStatement]:
        cnpj = self._resolve_cnpj(ticker)
        if cnpj is None:
            raise FundamentalsNotFoundError(
                f"No CVM filer is known for {ticker}; it may be a BDR, an "
                f"ETF or a fund, none of which file a DFP."
            )
        normalised = normalise_cnpj(cnpj)

        last = self._last_year if self._last_year is not None else _current_year()
        statements: list[FinancialStatement] = []
        for year in range(self._first_year, last + 1):
            statement = self._statement_for(normalised, year)
            if statement is not None:
                statements.append(statement)

        if not statements:
            raise FundamentalsNotFoundError(
                f"CVM filed no annual statement for {ticker} "
                f"(CNPJ {normalised}) between {self._first_year} and {last}."
            )
        statements.sort(key=lambda item: item.reference_date)
        return statements

    # -- internals ---------------------------------------------------

    def _statement_for(self, cnpj: str, year: int) -> FinancialStatement | None:
        archive_path = self._archive.fetch(year)
        if archive_path is None:
            return None

        try:
            with zipfile.ZipFile(archive_path) as archive:
                income = _company_rows(archive, INCOME, year, cnpj)
                if not income:
                    return None
                liabilities = _company_rows(archive, BALANCE_LIABILITIES, year, cnpj)
                assets = _company_rows(archive, BALANCE_ASSETS, year, cnpj)
                value_added = _company_rows(archive, VALUE_ADDED, year, cnpj)
        except zipfile.BadZipFile as exc:
            raise InvalidFundamentalsResponseError(
                f"CVM archive for {year} is not a readable ZIP: {exc}"
            ) from exc

        reference_date = _period_end(income, year)
        if reference_date is None:
            return None

        ebit = _amount(income, EBIT)
        depreciation = _amount(value_added, DEPRECIATION)

        return FinancialStatement(
            reference_date=reference_date,
            revenue=_amount(income, REVENUE),
            ebitda=_ebitda(ebit, depreciation),
            net_income=(
                _amount(income, NET_INCOME_OWNERS)
                # A company with no minority interests may report only the
                # consolidated line. Falling back is safe there and only
                # there, because the two are equal when there is nothing
                # to attribute elsewhere.
                or _amount(income, NET_INCOME_CONSOLIDATED)
            ),
            equity=_equity(liabilities),
            debt=_sum(liabilities, DEBT_CURRENT, DEBT_NON_CURRENT),
            cash=_amount(assets, CASH),
            free_cash_flow=None,  # see the module docstring
            ebit=ebit,
            income_before_tax=_amount(income, INCOME_BEFORE_TAX),
            income_tax_expense=_amount(income, INCOME_TAX),
        )


# -- parsing helpers -------------------------------------------------


def normalise_cnpj(cnpj: str) -> str:
    """The CNPJ punctuated the way the CVM writes it.

    The market data vendor returns bare digits (`33000167000101`) and the
    CVM files are keyed on `33.000.167/0001-01`. Comparing the two
    without normalising matches nothing at all — silently, since a
    company that filed nothing and a company whose key was mistyped look
    identical downstream.
    """
    digits = "".join(character for character in cnpj if character.isdigit())
    if len(digits) != 14:
        raise InvalidFundamentalsResponseError(
            f"CNPJ {cnpj!r} does not have 14 digits."
        )
    return f"{digits[0:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"


def _company_rows(
    archive: zipfile.ZipFile, statement: str, year: int, cnpj: str
) -> list[dict[str, str]]:
    """Rows for one company, from the latest version of the filing.

    Restatements are what `VERSAO` exists for: a company that re-delivers
    a year gets a higher version, and the older rows stay in the file.
    Reading them all would double every figure.
    """
    name = f"dfp_cia_aberta_{statement}_{year}.csv"
    try:
        raw = archive.read(name)
    except KeyError:
        return []

    reader = csv.DictReader(io.StringIO(raw.decode("latin-1")), delimiter=";")
    rows = [
        row
        for row in reader
        if row.get("CNPJ_CIA") == cnpj and row.get("ORDEM_EXERC") == CURRENT_PERIOD
    ]
    if not rows:
        return []

    latest = max(_version(row) for row in rows)
    return [row for row in rows if _version(row) == latest]


def _version(row: dict[str, str]) -> int:
    try:
        return int(row.get("VERSAO") or 0)
    except ValueError:
        return 0


def _period_end(rows: list[dict[str, str]], year: int) -> date | None:
    for row in rows:
        raw = row.get("DT_FIM_EXERC") or row.get("DT_REFER")
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError as exc:
                raise InvalidFundamentalsResponseError(
                    f"CVM {year} filing has an unreadable period end {raw!r}."
                ) from exc
    return None


def _amount(rows: list[dict[str, str]], code: str) -> Decimal | None:
    """The value of one account, scaled to whole reais.

    `None` when the company did not report that line — which is normal:
    a bank has no `2.01.04`, and rule 44 forbids substituting a zero for
    a figure nobody filed.
    """
    for row in rows:
        if row.get("CD_CONTA") != code:
            continue
        raw = row.get("VL_CONTA")
        if raw is None or raw.strip() == "":
            return None
        try:
            value = Decimal(raw.strip())
        except InvalidOperation as exc:
            raise InvalidFundamentalsResponseError(
                f"CVM account {code} has an unreadable amount {raw!r}."
            ) from exc
        return value * _scale(row)
    return None


def _scale(row: dict[str, str]) -> Decimal:
    scale = (row.get("ESCALA_MOEDA") or "").strip().upper()
    multiplier = SCALE_MULTIPLIERS.get(scale)
    if multiplier is None:
        raise InvalidFundamentalsResponseError(
            f"CVM reported an unrecognised currency scale {scale!r}."
        )
    return multiplier


def _sum(rows: list[dict[str, str]], *codes: str) -> Decimal | None:
    """The total of several accounts, or `None` if none was reported.

    A partial total is returned when only some parts exist — for debt,
    a company with no current borrowings genuinely has only the
    non-current line, and treating that as unreported would lose a real
    figure.
    """
    parts = [amount for code in codes if (amount := _amount(rows, code)) is not None]
    if not parts:
        return None
    return sum(parts, Decimal(0))


def _equity(rows: list[dict[str, str]]) -> Decimal | None:
    """Equity attributable to the parent's shareholders.

    Total consolidated equity less non-controlling interests, so it pairs
    with `3.11.01` on the income side. Without the netting, ROE would be
    computed from two populations of owners.
    """
    total = _amount(rows, EQUITY_TOTAL)
    if total is None:
        return None
    minority = _amount(rows, EQUITY_MINORITY)
    return total if minority is None else total - minority


def _ebitda(ebit: Decimal | None, depreciation: Decimal | None) -> Decimal | None:
    """`EBIT + |D&A|`; `None` unless both parts were reported."""
    if ebit is None or depreciation is None:
        return None
    return ebit + abs(depreciation)


def _current_year() -> int:
    """The latest year a DFP could exist for.

    Reads a clock, which every other module here avoids — but the set of
    published years genuinely depends on today, and the alternative is
    making every caller pass a year they would have to compute the same
    way. `CvmFundamentalsProvider` takes `last_year` so tests never
    depend on it.
    """
    from datetime import UTC, datetime

    return datetime.now(UTC).year
