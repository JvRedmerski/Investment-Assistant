"""Fundamental indicator calculation.

A pure, deterministic, I/O-free module (AGENTS.md rule 68 — testable with
known input and known expected output). Persistence lives in
`service.py`; nothing here touches a database or a provider.

## Missing-data policy

Every indicator returns `None` when any input it needs is absent, or when
its denominator is zero. `None` means "not computable from the data we
have" and must never be read as zero, nor substituted by a default
(AGENTS.md rule 44 — never invent a figure). A wrong number that looks
plausible is worse than an honest gap, because a score built on it would
look equally plausible.

## Inputs not ingested

`IndicatorInputs` declares one field the system does not collect, so the
formula that needs it is written, tested and ready — it simply returns
`None` until a per-period source exists:

**Every input is now ingested.** The table that used to sit here listed
`dividends_per_share` as the last gap; EVENTS-001 closed it, and all ten
formulas have a real source.

Brapi's `dividendYield` is a **present-day snapshot with no period end
date**. Applying it to a 2010 statement would attribute a present fact to
a past period — the point-in-time violation AGENTS.md rules 108/109
forbid. The CVM does report dividends charged to equity per year, in the
DMPL at `5.04.06` and `5.04.07`, which is the route to a real `dy`; it is
not ingested yet and is registered as future work.

The other three inputs arrived, and the formulas that had been waiting on
them started producing values with no change to this module:

- **`ebitda`** (W09-002) — Brapi's `cleanEbitda` was byte-identical to
  `ebit` in all 16 periods returned, so it was not EBITDA at all. The CVM
  allows deriving it (`EBIT + |D&A|`), which unblocked `debt_ebitda` and
  `ebitda_margin`.
- **`shares_outstanding`** (W09-003) — per fiscal year, from the CVM's
  `composicao_capital`, which unblocked `pe` and `pb`. The vendor only
  ever had a present-day count, with the same look-ahead problem
  `dividendYield` still has.
- **`ebit`, `income_before_tax`, `income_tax_expense`** (W06-003) —
  unblocked `roic`.

## Units

Margins, growth rates, ROE, ROIC and DY are **fractions**, not
percentages: 0.15 means 15%. Formatting is a presentation concern.
Multiples (P/L, P/VP, Dívida/EBITDA) are dimensionless ratios.

Values are computed in `Decimal` and converted to `float` only at the
boundary, because `financial_indicators` stores ratios, not currency
(ADR-003).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DivisionByZero, InvalidOperation


@dataclass(frozen=True)
class IndicatorInputs:
    """Everything one reference period needs, gathered from every source.

    Fields default to `None` so a caller only supplies what it actually
    has; see the module docstring for which ones are not ingested yet.
    """

    reference_date: date

    # From `fundamentals` (W06-001).
    revenue: Decimal | None = None
    ebitda: Decimal | None = None
    net_income: Decimal | None = None
    equity: Decimal | None = None
    debt: Decimal | None = None
    cash: Decimal | None = None
    free_cash_flow: Decimal | None = None

    # From `asset_prices`: the close on the reference date, or the most
    # recent one before it. Never a later price (AGENTS.md rule 108).
    price: Decimal | None = None

    # From `fundamentals`, added in W06-003. The tax figures are kept as
    # reported so the effective rate is derived per period rather than
    # assumed (ADR-014).
    ebit: Decimal | None = None
    income_before_tax: Decimal | None = None
    income_tax_expense: Decimal | None = None

    # From `fundamentals`, added in W09-003: the count at this period's
    # end, not today's. That distinction is the whole reason `pe` and
    # `pb` were absent until now (rules 108/109).
    shares_outstanding: Decimal | None = None

    # From `fundamentals`, added in EVENTS-001: what the company
    # charged to equity as distributions during this period, dividends
    # plus interest on capital. Aggregate rather than per share, for the
    # same reason `net_income` and `equity` are: the per-share figure is
    # derived below, from the count that belongs to the same period.
    dividends_paid: Decimal | None = None


@dataclass(frozen=True)
class IndicatorSet:
    """The computed indicators for one reference period.

    `None` on any field means "not computable", never zero.
    """

    pe: float | None = None
    pb: float | None = None
    roe: float | None = None
    roic: float | None = None
    dy: float | None = None
    debt_ebitda: float | None = None
    net_margin: float | None = None
    ebitda_margin: float | None = None
    revenue_growth: float | None = None
    profit_growth: float | None = None


def compute_indicators(
    current: IndicatorInputs,
    previous: IndicatorInputs | None = None,
) -> IndicatorSet:
    """Derive the indicator set for `current`.

    `previous` is the immediately preceding reference period, needed only
    by the growth indicators; without it they are `None`.

    Formulas (periodicity: annual, matching the statements ingested):

    - **pe** (P/L) = price / earnings per share, where EPS =
      net_income / shares_outstanding.
    - **pb** (P/VP) = price / book value per share, where BVPS =
      equity / shares_outstanding.
    - **roe** = net_income / equity. Reported even when negative: a loss,
      or negative shareholders' equity, is a real and meaningful result.
    - **roic** = NOPAT / invested capital, where NOPAT =
      ebit × (1 − effective tax rate), the effective rate is
      |income_tax_expense| / income_before_tax for that same period, and
      invested capital = debt + equity − cash.
    - **dy** = (dividends_paid / shares_outstanding) / price.
    - **debt_ebitda** = debt / ebitda.
    - **net_margin** = net_income / revenue.
    - **ebitda_margin** = ebitda / revenue.
    - **revenue_growth** = (revenue − prior revenue) / prior revenue.
    - **profit_growth** = (net_income − prior net_income) / prior
      net_income.
    """
    eps = _ratio_decimal(current.net_income, current.shares_outstanding)
    bvps = _ratio_decimal(current.equity, current.shares_outstanding)
    dps = _ratio_decimal(current.dividends_paid, current.shares_outstanding)

    return IndicatorSet(
        pe=_to_float(_ratio_decimal(current.price, eps)),
        pb=_to_float(_ratio_decimal(current.price, bvps)),
        roe=_to_float(_ratio_decimal(current.net_income, current.equity)),
        roic=_to_float(_ratio_decimal(_nopat(current), _invested_capital(current))),
        dy=_to_float(_ratio_decimal(dps, current.price)),
        debt_ebitda=_to_float(_ratio_decimal(current.debt, current.ebitda)),
        net_margin=_to_float(_ratio_decimal(current.net_income, current.revenue)),
        ebitda_margin=_to_float(_ratio_decimal(current.ebitda, current.revenue)),
        revenue_growth=_to_float(
            _growth(current.revenue, previous.revenue if previous else None)
        ),
        profit_growth=_to_float(
            _growth(current.net_income, previous.net_income if previous else None)
        ),
    )


# -- helpers ---------------------------------------------------------


def _ratio_decimal(
    numerator: Decimal | None, denominator: Decimal | None
) -> Decimal | None:
    """`numerator / denominator`, or `None` if that is not meaningful.

    Returns `None` when either side is missing or the denominator is
    zero — never raises, never yields infinity or NaN (requirement:
    division by zero must not produce a value).
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    try:
        return numerator / denominator
    except (DivisionByZero, InvalidOperation):  # pragma: no cover - defensive
        return None


def _growth(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    """Period-over-period growth as a fraction of the prior value.

    Returns `None` when the prior value is missing, zero, **or negative**.
    Growth measured against a negative base is not interpretable as a
    percentage: a company improving from a loss of 100 to a loss of 50
    would report "+50% growth" while still losing money. Rather than emit
    a number that reads as good news, this reports "not computable" and
    lets the caller handle the turnaround case explicitly.
    """
    if current is None or previous is None or previous <= 0:
        return None
    return (current - previous) / previous


def _effective_tax_rate(inputs: IndicatorInputs) -> Decimal | None:
    """The period's actual tax burden as a fraction of pre-tax income.

    Derived from the two figures as reported, never assumed. Brapi's own
    `cleanNopat` applies a flat 34% to every period, while the real
    effective rates for PETR4 range from 26.6% to 32.4% — a gap large
    enough to move ROIC materially, which is why this is computed rather
    than taken from the provider (ADR-014).

    The sign matters. Tax expense is reported as a negative number (a
    deduction), so the rate is `-expense / pre-tax income`. A *positive*
    expense is a tax benefit, and negating it yields a negative rate,
    correctly signalling a credit rather than a burden.

    Returns `None` when the result is not usable as a rate:

    - either figure missing;
    - pre-tax income not positive — in a loss-making year the ratio is
      not a tax rate at all;
    - the rate falls outside [0, 1]. `NOPAT = ebit × (1 − t)` is only
      meaningful in that band; outside it the formula would inflate NOPAT
      beyond EBIT or flip its sign. A rate outside the band means the two
      reported figures are inconsistent or the period was extraordinary,
      not that we learned something about profitability. Petrobras 2020
      is the real case that exposed this: a R$ 6.2bn tax *benefit* against
      R$ 37m of pre-tax income implies a rate of −16,780%, which turned
      ROIC into −1096% before this guard existed.
    """
    if inputs.income_before_tax is None or inputs.income_tax_expense is None:
        return None
    if inputs.income_before_tax <= 0:
        return None

    rate = -inputs.income_tax_expense / inputs.income_before_tax
    if rate < 0 or rate > 1:
        return None
    return rate


def _nopat(inputs: IndicatorInputs) -> Decimal | None:
    """Net operating profit after tax = ebit × (1 − effective tax rate)."""
    tax_rate = _effective_tax_rate(inputs)
    if inputs.ebit is None or tax_rate is None:
        return None
    return inputs.ebit * (Decimal(1) - tax_rate)


def _invested_capital(inputs: IndicatorInputs) -> Decimal | None:
    """Invested capital = debt + equity − cash.

    Requires all three: omitting one would understate or overstate the
    base and quietly distort ROIC.
    """
    if inputs.debt is None or inputs.equity is None or inputs.cash is None:
        return None
    return inputs.debt + inputs.equity - inputs.cash


def _to_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)
