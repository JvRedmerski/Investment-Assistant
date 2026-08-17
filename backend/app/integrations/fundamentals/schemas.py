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

    @property
    def reported_fields(self) -> dict[str, Decimal]:
        """The subset of figures actually reported (non-null)."""
        return {
            name: value
            for name, value in (
                ("revenue", self.revenue),
                ("ebitda", self.ebitda),
                ("net_income", self.net_income),
                ("equity", self.equity),
                ("debt", self.debt),
                ("cash", self.cash),
                ("free_cash_flow", self.free_cash_flow),
            )
            if value is not None
        }
