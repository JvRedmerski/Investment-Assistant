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

## Shares outstanding, and the unit the file forgets to state

`composicao_capital` carries the share count per fiscal year — which is
the whole reason P/L and P/VP can be computed at all, since the vendor
only ever published a present-day snapshot with no period attached
(rules 108/109). Outstanding is `QT_ACAO_TOTAL_CAP_INTEGR` less
`QT_ACAO_TOTAL_TESOURO`: treasury shares receive no dividend and hold no
claim on earnings, so counting them would understate EPS.

That file has **no `ESCALA_MOEDA` column**, and filers do not agree on a
unit. Measured across the 2020-2025 archives, roughly a third write the
count in thousands and the rest in units, with no marker distinguishing
them — and companies switch between filings. Petrobras is one: its 2020
file says `13,044,497` and its 2021 file says `13,044,496,930`, the same
count a thousand times apart.

Taken at face value, that error is not a small one. A count a thousand
times too low makes EPS a thousand times too high, which makes P/L a
thousand times too low, which on the inverted valuation scale clamps to
a **perfect score**. The most broken readings would sort to the top of
any ranking built on them.

So the unit is not assumed, it is reconciled against the filing itself.
The income statement reports earnings per share at `3.99.*`, in reais
per share, and `net_income / EPS` gives an independent count. The filed
number is accepted in whichever unit reconciles with it, and where
neither does — or where the filing reports no EPS to check against —
`shares_outstanding` stays `None`. An absent Valuation pillar is a state
the scoring engine handles as normal; a valuation built on a
thousand-fold error is not.

The tolerance is deliberately loose (a factor of five either way),
because the two counts are not the same quantity: EPS uses the weighted
average over the year and is reported per share class, while the filed
count is the total at the period end. It only has to be tight enough to
tell one unit from another, and a factor of five is two orders of
magnitude clear of a factor of a thousand.

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
#: Statement of changes in equity. Shaped unlike the others: every
#: account is repeated once per equity column, so a row is identified by
#: `CD_CONTA` *and* `COLUNA_DF`.
EQUITY_CHANGES = "DMPL_con"

#: The share count file. Not a statement: it has no account codes, no
#: `ORDEM_EXERC` and no currency scale, and holds one row per company.
CAPITAL_COMPOSITION = "composicao_capital"
SHARES_ISSUED_COLUMN = "QT_ACAO_TOTAL_CAP_INTEGR"
SHARES_TREASURY_COLUMN = "QT_ACAO_TOTAL_TESOURO"

#: The DMPL column holding equity attributable to the parent. Written
#: exactly like this in the file, accents included. `Patrimônio Líquido
#: Consolidado` is the sibling that *includes* non-controlling interests,
#: and picking it would count distributions to owners the shareholder
#: does not have — the same trap as `3.11` versus `3.11.01`.
EQUITY_COLUMN = "Patrimônio Líquido"

#: Distributions charged to equity during the period. Both are debits,
#: so the filing writes them negative.
DIVIDENDS = "5.04.06"
INTEREST_ON_CAPITAL = "5.04.07"

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

#: Earnings per share, in reais per share. Every account under this
#: prefix is one: `3.99.01.01`/`3.99.01.02` are basic EPS per share
#: class, `3.99.02.*` diluted, and the shorter codes are the headers
#: above them. Used only to reconcile the unit of the share count.
#:
#: ⚠️ These carry `ESCALA_MOEDA` like every other row and it does **not**
#: apply to them: Petrobras' 2024 basic EPS reads `2.84` on a row marked
#: `MIL`, and R$ 2.84 is the figure the company published. Read raw.
EARNINGS_PER_SHARE_PREFIX = "3.99"

#: The two units filers write share counts in. There is no third: every
#: count in the 2020-2025 archives reconciles at one of these or at
#: neither.
SHARE_COUNT_UNITS = (Decimal(1), Decimal(1000))

#: How far the filed count may sit from the one its own EPS implies and
#: still be accepted. Wide because the two are different quantities —
#: year-end total against weighted average per class — and it only has to
#: separate units, not verify a figure. See the module docstring.
SHARE_COUNT_TOLERANCE_LOW = Decimal("0.2")
SHARE_COUNT_TOLERANCE_HIGH = Decimal(5)


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
                equity_changes = _company_rows(archive, EQUITY_CHANGES, year, cnpj)
                capital = _capital_row(archive, year, cnpj)
        except zipfile.BadZipFile as exc:
            raise InvalidFundamentalsResponseError(
                f"CVM archive for {year} is not a readable ZIP: {exc}"
            ) from exc

        reference_date = _period_end(income, year)
        if reference_date is None:
            return None

        ebit = _amount(income, EBIT)
        depreciation = _amount(value_added, DEPRECIATION)
        net_income = _amount(income, NET_INCOME_OWNERS) or _amount(
            income, NET_INCOME_CONSOLIDATED
        )

        return FinancialStatement(
            reference_date=reference_date,
            revenue=_amount(income, REVENUE),
            ebitda=_ebitda(ebit, depreciation),
            # A company with no minority interests may report only the
            # consolidated line. Falling back is safe there and only
            # there, because the two are equal when there is nothing to
            # attribute elsewhere.
            net_income=net_income,
            equity=_equity(liabilities),
            debt=_sum(liabilities, DEBT_CURRENT, DEBT_NON_CURRENT),
            cash=_amount(assets, CASH),
            free_cash_flow=None,  # see the module docstring
            ebit=ebit,
            income_before_tax=_amount(income, INCOME_BEFORE_TAX),
            income_tax_expense=_amount(income, INCOME_TAX),
            shares_outstanding=_shares_outstanding(
                capital, income, net_income, reference_date
            ),
            dividends_paid=_distributions(equity_changes),
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


def _capital_row(
    archive: zipfile.ZipFile, year: int, cnpj: str
) -> dict[str, str] | None:
    """The company's share count row, or `None` if it filed none.

    A different shape from the statement files and read separately for
    that reason: one row per company rather than one per account, no
    `ORDEM_EXERC` and no `CD_CONTA`. `VERSAO` still applies, and the
    archives hold exactly one row per company per year, so taking the
    highest version is a guard rather than a filter.
    """
    name = f"dfp_cia_aberta_{CAPITAL_COMPOSITION}_{year}.csv"
    try:
        raw = archive.read(name)
    except KeyError:
        return None

    reader = csv.DictReader(io.StringIO(raw.decode("latin-1")), delimiter=";")
    rows = [row for row in reader if row.get("CNPJ_CIA") == cnpj]
    if not rows:
        return None
    return max(rows, key=_version)


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


def _distributions(equity_changes: list[dict[str, str]]) -> Decimal | None:
    """Dividends plus interest on capital charged to equity in the period.

    The DMPL is the only statement that says what was actually
    distributed *for* a period, dated to that period — which is what a
    point-in-time yield needs and what a vendor's present-day
    `dividendYield` snapshot can never provide (rules 108/109).

    Three things decide whether this number is right.

    **The column.** Every DMPL account is repeated once per equity
    column, so `CD_CONTA` alone selects eight rows. Only
    `Patrimônio Líquido` is read: its sibling `Patrimônio Líquido
    Consolidado` adds distributions made to non-controlling interests,
    which the shareholder has no claim on. It is the same distinction
    that makes `net_income` `3.11.01` rather than `3.11` — every figure
    in a statement here describes the parent's owners.

    **The sign.** A distribution is a debit to equity, so the filing
    writes it negative. The magnitude is the quantity; the sign is
    presentation, exactly as with D&A in the value-added statement.

    **What is left out.** `5.04.11` (*dividendos prescritos*) is money
    returning to the company because shareholders never claimed it —
    a reversal of some earlier period's distribution, not a negative
    distribution of this one. Netting it here would understate the
    period that paid and misattribute the correction. PETR4's 2024
    filing carries R$ 316 M of it.

    Interest on capital is summed with dividends because both are cash
    leaving equity for shareholders. They differ in tax treatment, not
    in whether the holder received them, and several filers report the
    whole payout under one code and nothing under the other.
    """
    parts = [
        amount
        for code in (DIVIDENDS, INTEREST_ON_CAPITAL)
        if (amount := _amount_in_column(equity_changes, code, EQUITY_COLUMN))
        is not None
    ]
    if not parts:
        return None
    return abs(sum(parts, Decimal(0)))


def _amount_in_column(
    rows: list[dict[str, str]], code: str, column: str
) -> Decimal | None:
    """`_amount`, but for a statement whose accounts repeat per column."""
    return _amount([row for row in rows if row.get("COLUNA_DF") == column], code)


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


def _shares_outstanding(
    capital: dict[str, str] | None,
    income: list[dict[str, str]],
    net_income: Decimal | None,
    reference_date: date,
) -> Decimal | None:
    """Shares in circulation at the period end, in the unit the filing meant.

    Issued capital less treasury, then reconciled against the earnings
    per share the same filing reports — because `composicao_capital`
    states no scale and filers use two different ones. The module
    docstring has the evidence; the short version is that a third of
    filings write the count in thousands, unmarked, and swallowing that
    would produce a P/L a thousand times too low, which scores as the
    cheapest share on the exchange.

    `None` whenever the count cannot be trusted, which covers four real
    cases seen in the archives:

    - no row filed, or the count columns empty;
    - a count of zero, or treasury exceeding issued capital (nine
      companies across 2020-2025), which is arithmetic that describes no
      company;
    - a filing with no EPS to check the unit against;
    - a count that reconciles at neither unit — six to seventeen filings
      a year, whose two figures simply contradict each other.

    Absent, never approximated (rule 44). The Valuation pillar already
    treats an absent input as a first-class state.
    """
    if capital is None:
        return None
    if (capital.get("DT_REFER") or "").strip() != reference_date.isoformat():
        # The count would be attached to a period it does not describe.
        # Never observed in 2020-2025, where the two dates agree for
        # every company in the file, but silently mis-dating a figure is
        # exactly what rule 109 exists to prevent.
        return None

    issued = _count(capital, SHARES_ISSUED_COLUMN)
    treasury = _count(capital, SHARES_TREASURY_COLUMN)
    if issued is None or treasury is None:
        return None
    filed = issued - treasury
    if filed <= 0:
        return None

    implied = _implied_share_count(income, net_income)
    if implied is None:
        return None

    for unit in SHARE_COUNT_UNITS:
        ratio = (filed * unit) / implied
        if SHARE_COUNT_TOLERANCE_LOW <= ratio <= SHARE_COUNT_TOLERANCE_HIGH:
            return filed * unit
    return None


def _implied_share_count(
    income: list[dict[str, str]], net_income: Decimal | None
) -> Decimal | None:
    """The share count the filing's own earnings per share implies.

    `|net_income| / |EPS|`. Only ever used to tell one unit from another,
    so the largest EPS reported is taken when a company files one per
    share class: any of them lands within a small factor of the true
    count, and the question being asked is three orders of magnitude
    coarser than that.
    """
    if net_income is None or net_income == 0:
        return None

    per_share = [
        value
        for row in income
        if (row.get("CD_CONTA") or "").startswith(EARNINGS_PER_SHARE_PREFIX)
        # Read raw: `ESCALA_MOEDA` does not apply to a per-share figure,
        # however the row is marked. See the constant.
        and (value := abs(_raw_decimal(row))) > 0
    ]
    if not per_share:
        return None
    return abs(net_income) / max(per_share)


def _count(row: dict[str, str], column: str) -> Decimal | None:
    """A whole-number column, or `None` when it was left blank."""
    raw = (row.get(column) or "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise InvalidFundamentalsResponseError(
            f"CVM column {column} has an unreadable count {raw!r}."
        ) from exc


def _raw_decimal(row: dict[str, str]) -> Decimal:
    """`VL_CONTA` exactly as written, with no currency scale applied."""
    raw = (row.get("VL_CONTA") or "").strip()
    if not raw:
        return Decimal(0)
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise InvalidFundamentalsResponseError(
            f"CVM account {row.get('CD_CONTA')!r} has an unreadable " f"amount {raw!r}."
        ) from exc


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
