"""Data transfer objects returned by a `FundamentalsProvider`.

Provider-agnostic: nothing here (or in `base.py`) knows about Brapi.
Pydantic validates data coming from an external, untrusted source
(AGENTS.md rule 19 — never assume a field exists or is well-formed).

Every monetary field is optional: a real filing may genuinely not report
a line item, and a provider may simply not expose it. `None` means "not
available", and must never be silently replaced by a default or by a
value from a different period (AGENTS.md rule 44 — never invent data;
rule 109 — a figure must belong to the reference date it is stored
under).
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class FinancialStatement(BaseModel):
    """One company's reported figures for a single reference period.

    `reference_date` is the period end date reported by the source (the
    closing date of the fiscal year), and is the identity of the record
    together with the asset.
    """

    reference_date: date
    revenue: Decimal | None = None
    ebitda: Decimal | None = None
    net_income: Decimal | None = None
    equity: Decimal | None = None
    debt: Decimal | None = None
    cash: Decimal | None = None
    free_cash_flow: Decimal | None = None
    # Added in W06-003; the two tax figures are kept as reported so the
    # effective rate can be derived per period rather than assumed.
    ebit: Decimal | None = None
    income_before_tax: Decimal | None = None
    income_tax_expense: Decimal | None = None
    # Added in W09-003: shares in circulation at the period end, issued
    # capital less treasury. Not currency — a count — but reported by
    # the same filing and stored under the same reference date, which is
    # what makes P/L and P/VP computable without look-ahead.
    shares_outstanding: Decimal | None = None
    # Added in EVENTS-001: what the company charged to equity as
    # distributions during the period - dividends plus interest on
    # capital. Reported as a positive magnitude, though the filing
    # writes it as a debit (negative). Aggregate, not per share: the
    # per-share figure is derived at indicator time, the same way EPS
    # and book value per share are.
    dividends_paid: Decimal | None = None

    @property
    def reported_fields(self) -> dict[str, Decimal]:
        """The subset of figures actually reported (non-null)."""
        return {
            name: value
            for name in REPORTED_FIELD_NAMES
            if (value := getattr(self, name)) is not None
        }


#: Every figure a statement can carry. Kept as a single list so the data
#: quality checks cannot drift out of sync with the schema when a field
#: is added.
#:
#: All are monetary except `shares_outstanding`, which is a count. It
#: belongs here anyway, because what this list drives is "did the source
#: report this figure", and that question is the same for both.
REPORTED_FIELD_NAMES: tuple[str, ...] = (
    "revenue",
    "ebitda",
    "net_income",
    "equity",
    "debt",
    "cash",
    "free_cash_flow",
    "ebit",
    "income_before_tax",
    "income_tax_expense",
    "shares_outstanding",
    "dividends_paid",
)
