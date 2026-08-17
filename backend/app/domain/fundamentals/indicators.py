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

## Inputs not yet ingested

`IndicatorInputs` declares fields the system does not collect yet, so
the formulas that need them are written, tested, and ready — they simply
return `None` until W06-003 supplies the data:

| missing input       | indicators it blocks       |
|---------------------|----------------------------|
| shares_outstanding  | pe, pb                     |
| dividends_per_share | dy                         |
| ebit + tax rate     | roic                       |
| ebitda              | debt_ebitda, ebitda_margin |

`ebitda` is blocked for the reason recorded in ADR-013 (the provider only
exposes it as a trailing-twelve-months snapshot with no period end date,
which cannot be attributed to a reference date without look-ahead).

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

    # Not ingested yet — see module docstring.
    shares_outstanding: Decimal | None = None
    dividends_per_share: Decimal | None = None
    ebit: Decimal | None = None
    effective_tax_rate: Decimal | None = None


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
      ebit × (1 − effective_tax_rate) and invested capital =
      debt + equity − cash.
    - **dy** = dividends_per_share / price.
    - **debt_ebitda** = debt / ebitda.
    - **net_margin** = net_income / revenue.
    - **ebitda_margin** = ebitda / revenue.
    - **revenue_growth** = (revenue − prior revenue) / prior revenue.
    - **profit_growth** = (net_income − prior net_income) / prior
      net_income.
    """
    eps = _ratio_decimal(current.net_income, current.shares_outstanding)
    bvps = _ratio_decimal(current.equity, current.shares_outstanding)

    return IndicatorSet(
        pe=_to_float(_ratio_decimal(current.price, eps)),
        pb=_to_float(_ratio_decimal(current.price, bvps)),
        roe=_to_float(_ratio_decimal(current.net_income, current.equity)),
        roic=_to_float(_ratio_decimal(_nopat(current), _invested_capital(current))),
        dy=_to_float(_ratio_decimal(current.dividends_per_share, current.price)),
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


def _nopat(inputs: IndicatorInputs) -> Decimal | None:
    """Net operating profit after tax = ebit × (1 − effective tax rate).

    Both inputs are required. No default tax rate is assumed: picking one
    (e.g. Brazil's headline 34%) would silently bake a modelling
    assumption into a figure presented as measured (AGENTS.md rule 44).
    When EBIT is ingested, the tax-rate source becomes an explicit
    decision to make then.
    """
    if inputs.ebit is None or inputs.effective_tax_rate is None:
        return None
    return inputs.ebit * (Decimal(1) - inputs.effective_tax_rate)


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
