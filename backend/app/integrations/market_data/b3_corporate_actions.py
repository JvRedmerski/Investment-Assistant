"""`CorporateActionProvider` backed by B3's open corporate-events service.

https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/

This is the **magnitude**, and it is the last piece the wave was missing.
B3's end-of-day archive counts distributions and never sizes them
(ADR-025); this service publishes the size of each one — reais per share
for a payout, a factor for a split — free, without a token and without a
quota, which is why it was preferred to a paid vendor for the same reason
ADR-020 preferred the CVM's open filings to one.

Every claim below was measured against the live service and the cached
archives on 2026-08-20 before any of it was written down.

## What the source actually is

Not a documented open-data product like COTAHIST's yearly files or
`dados.cvm.gov.br`. It is the JSON backend of B3's public listed-company
pages: three GET endpoints whose **parameters are a base64-encoded JSON
object in the URL path**, not a query string. There is no authentication
and no rate limit published.

That shape is why this module is deliberately thin. It is an adapter over
one service, and `CorporateActionProvider` is the seam: if B3 changes the
endpoints, this file is what breaks, callers keep compiling, and the
system degrades to *absent magnitudes* — which is exactly the state the
project was in before this task, and never to a wrong number.

Three calls, because the service splits by question:

- `GetInitialCompanies` resolves the four-letter issuer code taken from
  the ticker (`PETR4` -> `PETR`) into the `tradingName` the cash
  endpoint insists on (`PETROBRAS`). There is no way to ask the cash
  endpoint by code.
- `GetListedCashDividends` serves the **full** payout history, paginated,
  keyed by `tradingName` and discriminated by `typeStock` (`ON`, `PN`,
  `UNT`, `PNA`).
- `GetListedSupplementCompany` serves share events (`stockDividends`)
  keyed by ISIN, plus a short tail of recent cash payouts used only as a
  fallback — see below.

## The join is the ISIN, and getting it wrong cubes the answer

B3 repeats one share event **once per ISIN the issuer has ever had**.
BBAS3's 1:2 split of 2024-04-16 arrives three times, under
`BRBBASA04OR8`, `BRBBASA05OR5` and `BRBBASACNOR3`; only the last is the
paper that trades. Composing all three gives 8.0 against a measured price
step of 2.02.

This was not a subtle failure. While the reading was being validated,
*every* disagreement with a real price step turned out to be an exact
power of the right answer — 2^3 for BBAS3, 4^3 for BPAC11, 10^3 for
CPLE3, 1.1^3 for UNIP3 — which is what pointed at duplication rather than
at a wrong factor. Filtering on the ISIN printed by the archive on the
paper's own records (`CODISI`, see `SecurityIdentity`) takes agreement
from 32/50 to **49/50** across the papers checked, and the one remaining
outlier is IRBR3's 1:30 regroup at R$0.93, where a price a few ticks wide
cannot measure a factor at all.

## `factor` means two different things, and the label is what says which

Measured against real price steps rather than assumed:

| label | reading | check |
|---|---|---|
| `DESDOBRAMENTO` | `1 + factor/100` | BBAS3 `100` -> 2.00 vs 2.0229 measured |
| `BONIFICACAO` | `1 + factor/100` | ITUB4 `3` -> 1.03 vs 1.0297 |
| `GRUPAMENTO` | `factor` itself | MGLU3 `0.10` -> 0.10 vs 0.1004 |

A percentage in two labels and a bare ratio in the third, under one field
name. The rest of the labels the service uses — `CIS RED CAP`,
`INCORPORACAO`, `RESG TOTAL RV`, `REST CAP ACOES` — are **left unsized on
purpose**: ITUB4's `CIS RED CAP` of 2021-10-04 carries `factor` 100,
which under either reading would be 2.0 or 1.0 against a measured step of
**1.2190**. Whatever that number is, it is not a share ratio, and naming
it one would be rule 44. An unsized label makes the day's counted event
unaccounted for, which truncates the adjusted series rather than
corrupting it (ADR-026).

Several actions can land on one session and they **compose**: VIVT3 on
2025-04-15 is a `DESDOBRAMENTO` of 7,900 *and* a `GRUPAMENTO` of 0.025,
which multiply to exactly 2.0 against 2.0031 measured. That composition
belongs to whoever applies the actions, not here — this module reports
each one as filed.

## The unit trap, which is the same one twice already

`valueCash` is quoted per `quotedPerShares` shares, and that field is not
always `1`: **332 of 2,305** rows measured say `1000`. Reading it as
per-share would overstate those payouts a thousandfold — the identical
failure mode as `FATCOT` in the archive and `ESCALA_MOEDA` in the CVM
files. Dividing by it here matches how `cotahist.py` already normalises
price, so amount and price stay in the same unit.

In practice every per-1000 row observed predates 2008, from when B3
quoted shares by the lot; nothing in this project's window carries one.
It is handled anyway, because a silent thousandfold error is not
something to leave resting on a date range.

## Duplicates, and why identical rows are collapsed

The cash endpoint repeats rows: PETR returns 337 of which 323 are
distinct, VALE 150 of which 148 are. Rows are therefore reduced to the
values this project keeps, and identical tuples collapse. Two genuinely
separate payouts of the same kind, on the same date, for the same amount
would collapse too — but the service gives nothing that could tell them
apart from a duplicate, so counting them twice would be a guess in the
direction that corrupts, and collapsing is a guess in the direction that
merely understates.

## The fallback, and why it is not a merge

For a few issuers the cash endpoint answers nothing at all because
`tradingName` will not round-trip — `KLBN11`'s is `KLABIN S/A`, and the
slash defeats the lookup. Where that happens the supplement's own short
`cashDividends` tail is read instead. It is the *same service*, not a
second source, and it is used **instead of** the full endpoint and never
alongside it, so a period still comes whole from one place (ADR-020). The
tail is short, so the completeness check simply finds fewer accounted
sessions and reports a shorter adjustable window — visibly, which is the
point.
"""

import base64
import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Self

import httpx

from app.core.config import settings
from app.integrations.http import RetryingJsonClient
from app.integrations.market_data.base import CorporateActionProvider
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import (
    CorporateAction,
    CorporateActionKind,
    SecurityIdentity,
)

logger = logging.getLogger("investment_assistant.market_data.b3_corporate_actions")

#: Cash payout labels, as `corporateAction` writes them.
CASH_KIND_BY_LABEL = {
    "DIVIDENDO": CorporateActionKind.CASH_DIVIDEND,
    "JRS CAP PROPRIO": CorporateActionKind.INTEREST_ON_CAPITAL,
    "RENDIMENTO": CorporateActionKind.INCOME,
    "REST CAP DIN": CorporateActionKind.CAPITAL_RETURN,
}

#: Share event labels whose `factor` is a **percentage of new shares per
#: hundred held**, so the ratio is `1 + factor/100`.
PERCENT_LABELS = {
    "DESDOBRAMENTO": CorporateActionKind.SPLIT,
    "BONIFICACAO": CorporateActionKind.BONUS,
}

#: The one label whose `factor` is already the ratio.
RATIO_LABELS = {"GRUPAMENTO": CorporateActionKind.REVERSE_SPLIT}

#: Labels the service uses that this project refuses to size. See the
#: module docstring for ITUB4's `CIS RED CAP` at `factor` 100 against a
#: 1.2190 step — the number is real, its meaning is not established, and
#: an unsized action is safer than an invented one.
UNSIZED_LABELS = frozenset(
    {"CIS RED CAP", "INCORPORACAO", "RESG TOTAL RV", "REST CAP ACOES"}
)


class B3CorporateActionProvider(CorporateActionProvider):
    """`CorporateActionProvider` over B3's listed-company JSON service."""

    source_name = "b3_corporate_events"

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        min_request_interval: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = RetryingJsonClient(
            base_url=base_url or settings.B3_EVENTS_BASE_URL,
            timeout=(
                timeout if timeout is not None else settings.B3_EVENTS_TIMEOUT_SECONDS
            ),
            max_retries=(
                max_retries
                if max_retries is not None
                else settings.B3_EVENTS_MAX_RETRIES
            ),
            min_request_interval=(
                min_request_interval
                if min_request_interval is not None
                else settings.B3_EVENTS_MIN_REQUEST_INTERVAL_SECONDS
            ),
            not_found_error=TickerNotFoundError,
            unavailable_error=MarketDataUnavailableError,
            invalid_response_error=InvalidMarketDataResponseError,
            logger=logger,
            client=client,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_corporate_actions(
        self, security: SecurityIdentity, start: date, end: date
    ) -> list[CorporateAction]:
        if start > end:
            return []

        actions = [
            *self._share_actions(security, start, end),
            *self._cash_actions(security, start, end),
        ]
        actions.sort(key=lambda action: (action.last_date_prior, action.label))
        return actions

    # -- share events -------------------------------------------------

    def _share_actions(
        self, security: SecurityIdentity, start: date, end: date
    ) -> list[CorporateAction]:
        payload = self._supplement(security.ticker)
        rows = payload.get("stockDividends") or []
        if not isinstance(rows, list):
            raise InvalidMarketDataResponseError(
                f"B3 returned a non-list stockDividends for {security.ticker}."
            )

        actions: list[CorporateAction] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            # The ISIN filter is the whole reason this reading is
            # correct; see the module docstring.
            if str(row.get("isinCode") or "").strip() != security.isin:
                continue
            action = self._share_action(row, security.ticker)
            if action is not None and start <= action.last_date_prior <= end:
                actions.append(action)
        return _deduplicated(actions)

    def _share_action(self, row: dict[str, Any], ticker: str) -> CorporateAction | None:
        label = str(row.get("label") or "").strip()
        when = _parse_br_date(row.get("lastDatePrior"))
        if when is None:
            return None

        if label in UNSIZED_LABELS:
            logger.info(
                "B3 reports %s for %s on %s and this project does not size that "
                "label; the session stays unaccounted for.",
                label,
                ticker,
                when,
            )
            return None

        kind = PERCENT_LABELS.get(label) or RATIO_LABELS.get(label)
        if kind is None:
            logger.warning(
                "Unknown B3 stock event label %r for %s on %s — left unsized.",
                label,
                ticker,
                when,
            )
            return None

        factor = _parse_br_decimal(row.get("factor"))
        if factor is None or factor <= 0:
            return None

        ratio = (
            Decimal(1) + factor / Decimal(100) if label in PERCENT_LABELS else factor
        )
        return CorporateAction(
            last_date_prior=when, kind=kind, share_ratio=ratio, label=label
        )

    # -- cash payouts -------------------------------------------------

    def _cash_actions(
        self, security: SecurityIdentity, start: date, end: date
    ) -> list[CorporateAction]:
        rows = self._cash_rows(security.ticker)
        if rows is None:
            # The full endpoint could not be reached by name; fall back to
            # the supplement's own tail. Never both — see the docstring.
            rows = self._supplement(security.ticker).get("cashDividends") or []
            rows = [
                row
                for row in rows
                if isinstance(row, dict)
                and str(row.get("isinCode") or "").strip() == security.isin
            ]

        actions: list[CorporateAction] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            # `typeStock` is absent on the supplement tail, which is
            # already ISIN-filtered and therefore already this paper.
            type_stock = row.get("typeStock")
            if type_stock is not None and str(type_stock).strip() != (
                security.share_class
            ):
                continue
            action = self._cash_action(row, security.ticker)
            if action is not None and start <= action.last_date_prior <= end:
                actions.append(action)
        return _deduplicated(actions)

    def _cash_action(self, row: dict[str, Any], ticker: str) -> CorporateAction | None:
        # The full endpoint calls it `lastDatePriorEx`, the supplement
        # tail `lastDatePrior`, and they mean the same session.
        when = _parse_br_date(row.get("lastDatePriorEx") or row.get("lastDatePrior"))
        if when is None:
            return None

        label = str(row.get("corporateAction") or row.get("label") or "").strip()
        kind = CASH_KIND_BY_LABEL.get(label)
        if kind is None:
            logger.warning(
                "Unknown B3 cash payout label %r for %s on %s — left unsized.",
                label,
                ticker,
                when,
            )
            return None

        # The supplement tail names the per-share value `rate`.
        amount = _parse_br_decimal(row.get("valueCash") or row.get("rate"))
        if amount is None or amount <= 0:
            return None

        per_shares = _parse_br_decimal(row.get("quotedPerShares")) or Decimal(1)
        if per_shares <= 0:
            per_shares = Decimal(1)

        return CorporateAction(
            last_date_prior=when,
            kind=kind,
            cash_amount=amount / per_shares,
            label=label,
        )

    def _cash_rows(self, ticker: str) -> list[Any] | None:
        """Every cash payout row B3 holds, or `None` if it cannot be asked.

        `None` is distinct from an empty list: it means `tradingName`
        would not round-trip for this issuer, which is a lookup failure
        the caller answers by falling back, not the statement that the
        company never paid anything.
        """
        trading_name = self._trading_name(ticker)
        if trading_name is None:
            return None

        rows: list[Any] = []
        page = 1
        while True:
            payload = self._get(
                "GetListedCashDividends",
                {
                    "language": "pt-br",
                    "pageNumber": page,
                    "pageSize": _PAGE_SIZE,
                    "tradingName": trading_name,
                },
            )
            if not isinstance(payload, dict):
                raise InvalidMarketDataResponseError(
                    f"B3 returned an unexpected cash payout document for {ticker}."
                )
            rows.extend(payload.get("results") or [])

            pagination = payload.get("page") or {}
            total_pages = pagination.get("totalPages")
            if not isinstance(total_pages, int) or page >= total_pages:
                break
            page += 1
            if page > _MAX_PAGES:
                # Bounded rather than trusting a remote page count, so a
                # malformed document cannot spin here forever (rule 22).
                logger.warning(
                    "Stopped paging B3 cash payouts for %s at %s pages.",
                    ticker,
                    _MAX_PAGES,
                )
                break

        return rows or None

    def _trading_name(self, ticker: str) -> str | None:
        """The `tradingName` the cash endpoint keys on, from the ticker.

        A B3 negotiation code is four letters and a digit, and the
        letters are the issuer code the company search answers to.
        """
        code = ticker[:4].upper()
        payload = self._get(
            "GetInitialCompanies",
            {
                "language": "pt-br",
                "pageNumber": 1,
                "pageSize": _PAGE_SIZE,
                "company": code,
            },
        )
        if not isinstance(payload, dict):
            raise InvalidMarketDataResponseError(
                f"B3 returned an unexpected company document for {ticker}."
            )
        for row in payload.get("results") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("issuingCompany") or "").strip().upper() == code:
                name = str(row.get("tradingName") or "").strip()
                return name or None
        return None

    def _supplement(self, ticker: str) -> dict[str, Any]:
        payload = self._get(
            "GetListedSupplementCompany",
            {"issuingCompany": ticker[:4].upper(), "language": "pt-br"},
        )
        # The endpoint answers with a one-element list, and with an empty
        # one for a code it does not know.
        if isinstance(payload, list):
            if not payload:
                raise TickerNotFoundError(
                    f"B3's corporate-events service has no company for {ticker}."
                )
            payload = payload[0]
        if not isinstance(payload, dict):
            raise InvalidMarketDataResponseError(
                f"B3 returned an unexpected supplement document for {ticker}."
            )
        return payload

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        """One call, with the parameters base64-encoded into the path.

        Not a query string: this service reads a single base64 segment,
        which is why `RetryingJsonClient` is handed a path and no params.
        """
        encoded = base64.b64encode(
            json.dumps(params, ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        return self._client.get_json(f"/{endpoint}/{encoded}")


#: B3 accepts larger pages but answers slowly; 99 is what the site itself
#: asks for.
_PAGE_SIZE = 99

#: A ceiling on paging, so a malformed `totalPages` cannot loop forever.
#: The deepest history measured (ITUB, 954 rows) is 10 pages.
_MAX_PAGES = 50


def _deduplicated(actions: list[CorporateAction]) -> list[CorporateAction]:
    """Identical actions collapsed to one. See the module docstring."""
    seen: set[tuple[Any, ...]] = set()
    unique: list[CorporateAction] = []
    for action in actions:
        key = (
            action.last_date_prior,
            action.kind,
            action.cash_amount,
            action.share_ratio,
            action.label,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique


def _parse_br_date(value: Any) -> date | None:
    """`15/04/2024` as a `date`, or `None` if it is not one.

    Built by hand rather than with `strptime`, matching `cotahist.py`:
    the field is external input, a malformed one must not raise from
    inside a parse loop, and there is no timezone to get wrong here.
    """
    if not isinstance(value, str):
        return None
    parts = value.strip().split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    day, month, year = (int(part) for part in parts)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_br_decimal(value: Any) -> Decimal | None:
    """`7.900,00000000000` as a `Decimal`.

    Brazilian formatting: `.` groups thousands and `,` is the decimal
    separator, so the grouping is stripped before the comma is swapped.
    Getting that backwards turns 7,900 into 7.9.
    """
    if isinstance(value, int | float):
        return Decimal(str(value))
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Decimal(value.strip().replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None
