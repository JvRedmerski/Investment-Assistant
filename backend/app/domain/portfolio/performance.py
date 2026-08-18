"""Portfolio performance as a time-weighted index (AGENTS.md rule 26).

`app.quant.returns` deliberately stops short of this: it computes the
return of a *price series*, and says so, because a portfolio with
contributions is a different quantity. `(final - initial) / initial` over
a portfolio that received a R$ 1,000 contribution every month is
patrimonial variation — it would report a gain in a year the investor
actually lost money, since most of the growth was deposits.

This module produces the missing piece, and it produces it in the shape
everything else already consumes: a `PricePoint` series.

## What the series is

A **unit value** — the same device a fund uses for its cota. Start at
`base`, and move it only by the return the holdings produced, never by
money going in or out. Two portfolios that bought the same assets on the
same days get the same index whether one invested R$ 1,000 and the other
R$ 100,000.

Because it is a `PricePoint` series, every function in `app.quant` reads
it with no adapter: `total_return`, `cagr`, `volatility`, `max_drawdown`,
`beta`, `sharpe`, `sortino`. Time-weighting is also precisely what makes
it comparable with a benchmark, which has no cash flows to neutralise.

## What it is not: this is not portfolio value

Holdings are valued at `adjusted_close`, not at the market price of the
day, so a level here is not "what the portfolio was worth". The adjusted
close nets out dividends and splits, which is what makes the index a
*total return* — and it is the reason `DIVIDEND` rows are deliberately
not treated as cash flows below. The dividend is already in the adjusted
series; counting it again would credit it twice.

An investor asking "how much do I have" wants portfolio value, computed
from the raw close and including cash. That is a different number, and it
belongs to the dashboard work of Wave 11.

## Which movements count as flows

Portfolio value here means holdings only — this project derives no cash
balance (see `compute_net_contributions`). Under that definition:

- **BUY / SELL are external flows.** A purchase converts untracked cash
  into tracked holdings, so it raises the level without anything having
  performed. Neutralising it is the whole job.
- **DEPOSIT / WITHDRAWAL are not.** They move cash the index never sees.
- **DIVIDEND is not**, per the adjusted-close reasoning above.

Fees are folded into the flow, so they land where they belong: money that
went in without becoming value, which shows up as a lower return.

## Missing prices

A date on which any held asset has no stored price is **not valued** —
the level would be understated by exactly the missing holding, and a
fabricated valuation is what ADR-016 and rule 44 forbid. Gaps are normal
(the most recent session is often absent for a day), so this is the
common case rather than an error.

Any flow that happened on a skipped date is carried forward and
neutralised at the next date that can be valued, otherwise a purchase
made during a gap would be measured as performance.

That carry-forward is an **approximation, and it is the one weak point
of this module**. Subtracting the flow at the closing valuation treats
the money as if it arrived at the end of the sub-period, so anything the
newly bought shares gained in between is credited to the capital that was
already there. When the trade date can be valued — the normal case — the
sub-period ends exactly at the flow and there is no distortion at all.
The error only appears for a trade landing on a date no valuation exists
for, and it is bounded by that gap's length.

The alternatives are worse. Valuing the trade date at the transaction
price would fabricate a close (rule 44). Treating the gap as a zero
return would hide real market movement instead of misattributing it.
Reporting nothing would discard the whole history after one gap. The
honest fix is upstream: ingest the missing prices.
"""

from datetime import date
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum
from app.quant.returns import PricePoint

#: Starting level of the unit series.
#:
#: Cancels out of every derived quantity, as in `benchmarks.series`. 100
#: keeps a level readable as a percentage of the start.
DEFAULT_BASE = Decimal(100)

ZERO = Decimal(0)


def performance_index(
    transactions: list[Transaction],
    prices: dict[int, dict[date, Decimal]],
    as_of: date | None = None,
    base: Decimal = DEFAULT_BASE,
) -> list[PricePoint]:
    """The portfolio's time-weighted unit value, oldest first.

    `prices` maps `asset_id` to that asset's adjusted closes by date;
    `app.domain.benchmarks.comparison` builds it from `asset_prices`.
    Passing it in keeps this function pure and free of I/O (rule 68).

    Nothing after `as_of` is read (rule 108). The series starts at the
    first date the portfolio can be valued and holds something, so it is
    empty for a portfolio with no transactions, no stored prices, or only
    cash movements.

    A sub-period whose opening value is zero — before the first purchase,
    or after everything was sold — contributes no return: the level
    carries forward unchanged and the next measurable sub-period starts
    from the new value. Money that was out of the market earns nothing
    and loses nothing, rather than dividing by zero.
    """
    ordered = sorted(
        transactions, key=lambda tx: (tx.transaction_date.date(), tx.id or 0)
    )
    if not ordered:
        return []

    flows_by_date = _external_flows(ordered)
    quantities_by_date = _quantities_after_each_day(ordered)

    valuation_dates = _valuation_dates(prices, ordered[0], as_of)
    # Every day the ledger moved, in order. Walked with a pointer rather
    # than looked up by valuation date, because the two calendars do not
    # line up: a trade can land on a day no price exists for. Indexing by
    # the valuation date would then miss that day's holdings *and* its
    # flow, quietly valuing the portfolio as though the trade never
    # happened.
    ledger_days = sorted(set(flows_by_date) | set(quantities_by_date))

    points: list[PricePoint] = []
    level = base
    previous_value: Decimal | None = None
    pending_flow = ZERO
    held: dict[int, Decimal] = {}
    next_ledger_day = 0

    for day in valuation_dates:
        while (
            next_ledger_day < len(ledger_days) and ledger_days[next_ledger_day] <= day
        ):
            ledger_day = ledger_days[next_ledger_day]
            pending_flow += flows_by_date.get(ledger_day, ZERO)
            held = quantities_by_date.get(ledger_day, held)
            next_ledger_day += 1

        value = _value_on(held, prices, day)
        if value is None:
            # Not valuable today; the flow waits for a date that is.
            continue

        if previous_value is not None and previous_value > 0:
            level *= (value - pending_flow) / previous_value

        points.append(PricePoint(date=day, adjusted_close=level))
        previous_value = value
        pending_flow = ZERO

    return points


# -- helpers ---------------------------------------------------------


def _external_flows(ordered: list[Transaction]) -> dict[date, Decimal]:
    """Net money entering the tracked holdings, by date.

    Positive for a purchase (cash became holdings), negative for a sale.
    Fees are part of the flow on both sides: they are paid out of the
    investor's money and never become value.
    """
    flows: dict[date, Decimal] = {}
    for tx in ordered:
        if tx.type is TransactionTypeEnum.BUY:
            flow = tx.quantity * tx.price + tx.fees
        elif tx.type is TransactionTypeEnum.SELL:
            flow = -(tx.quantity * tx.price - tx.fees)
        else:
            # DEPOSIT / WITHDRAWAL never touch holdings; DIVIDEND is
            # already inside `adjusted_close` (see the module docstring).
            continue
        day = tx.transaction_date.date()
        flows[day] = flows.get(day, ZERO) + flow
    return flows


def _quantities_after_each_day(
    ordered: list[Transaction],
) -> dict[date, dict[int, Decimal]]:
    """Holdings as they stood at the end of each day the ledger moved.

    Only days with activity get an entry; `performance_index` carries the
    last known holdings forward across quiet days.
    """
    snapshots: dict[date, dict[int, Decimal]] = {}
    running: dict[int, Decimal] = {}

    for tx in ordered:
        if tx.asset_id is not None:
            if tx.type is TransactionTypeEnum.BUY:
                running[tx.asset_id] = running.get(tx.asset_id, ZERO) + tx.quantity
            elif tx.type is TransactionTypeEnum.SELL:
                # Never let the ledger drive a holding negative, matching
                # `compute_positions`: this stays a safe derivation of
                # whatever ledger it is handed.
                remaining = running.get(tx.asset_id, ZERO) - tx.quantity
                running[tx.asset_id] = max(remaining, ZERO)
        snapshots[tx.transaction_date.date()] = dict(running)

    return snapshots


def _valuation_dates(
    prices: dict[int, dict[date, Decimal]],
    first_transaction: Transaction,
    as_of: date | None,
) -> list[date]:
    """Every date any price is known for, from the first trade onward."""
    first_day = first_transaction.transaction_date.date()
    days = {
        day
        for by_date in prices.values()
        for day in by_date
        if day >= first_day and (as_of is None or day <= as_of)
    }
    return sorted(days)


def _value_on(
    held: dict[int, Decimal],
    prices: dict[int, dict[date, Decimal]],
    day: date,
) -> Decimal | None:
    """Total adjusted value of the holdings, or `None` if incomplete.

    `None` the moment one held asset lacks a price for the day: a partial
    total is not a smaller version of the right answer, it is a different
    portfolio.
    """
    total = ZERO
    for asset_id, quantity in held.items():
        if quantity <= 0:
            continue
        price = prices.get(asset_id, {}).get(day)
        if price is None:
            return None
        total += quantity * price
    return total
