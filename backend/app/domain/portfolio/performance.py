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
from the raw close. That is a different number, and `value_series` below
is it — a separate walk over a separate price map, deliberately not a
second output of the same one, so the two kinds of price never meet
inside one calculation. It still excludes cash, which this project does
not model (see `compute_net_contributions`).

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

## A flow is measured in the same currency the holdings are, and that is
## not the currency the investor paid in

Holdings are valued at `adjusted_close`, which is not the traded price:
for an asset that has paid six years of dividends the adjusted close is a
*fraction* of what the shares changed hands for. So a purchase adds
`quantity × adjusted_close` of value to this series, and never
`quantity × price`.

Subtracting the cash the investor spent instead is a unit error, and it
does not fail quietly. Measured on the real database, a portfolio of
PETR4 bought across 2020 produced an index level of **-3.88** — a unit
value cannot be negative — because each purchase subtracted roughly three
times the value it had added. Reduced to a minimum case: identical trades
with an identical +10% return give 100 → 100 → 110 when the adjustment
factor is 1, and 100 → **-100** → **-110** when it is 3.

The whole suite was blind to it, and could not have caught it: every
fixture priced the asset at exactly its traded price, which is the one
case where the two currencies coincide.

`_external_share_flows` is the fix. A flow is expressed in **shares** —
what the transaction added to or removed from the holdings — and valued
at the same adjusted close the holdings are valued at on the day it is
neutralised. Fees keep their drag by being converted at the price of
their own transaction: R$ 5 of fees on shares bought at R$ 10 is half a
share's worth of money that never became value.

## Missing prices

A date on which any held asset has no stored price is **not valued** —
the level would be understated by exactly the missing holding, and a
fabricated valuation is what ADR-016 and rule 44 forbid. Gaps are normal
(the most recent session is often absent for a day), so this is the
common case rather than an error.

Any flow that happened on a skipped date is carried forward and
neutralised at the next date that can be valued, otherwise a purchase
made during a gap would be measured as performance.

The flow is settled at the closing valuation, at that day's prices —
which is exact for the ordinary case and only approximate for one.

**Adding to something already held is exact**, however long the gap. The
flow and the holdings it joins are the same asset, so the unknown price
on the trade date appears in both sub-periods and cancels: buying 10 more
of a holding of 10 during a gap gives the same level whatever the market
did on the day nobody priced. That was not true while flows were
subtracted in cash — the mismatch there is what made the gap case wrong,
and fixing the unit fixed this too.

**Buying an asset the portfolio did not hold is approximate**, and now in
a way that only ever understates: whatever the new asset earned between
the trade and the next valuation is left out of the index rather than
credited to the capital that was already there. It is bounded by the
gap's length and it cannot compound into a wrong sign.

The alternatives are worse. Valuing the trade date at the transaction
price would fabricate a close (rule 44). Treating the gap as a zero
return would hide real market movement instead of leaving it out.
Reporting nothing would discard the whole history after one gap. The
honest fix is upstream: ingest the missing prices.

## Share actions restate the ledger twice, in opposite directions

A split moves a holding without a transaction, so both curves below have
to account for it — and they need **different** accounts of it, because
they price the holding differently. Getting this backwards produces a
number that is wrong by the whole factor and still plots as a smooth
line, which is the same failure mode as the currency mix this module's
docstring already warns about.

- `value_series` prices at the **raw close**, which is what printed on
  the day. Its quantities must therefore be the ones held **on that
  day**: a ratio applies going forward, from its ex-date onwards, exactly
  as custody experienced it.

- `performance_index` prices at **`adjusted_close`, which is quoted in
  today's shares** — the whole point of adjustment is that it restates
  history onto the current share count. Its quantities must be restated
  the same way, so a purchase made before a 1:2 split counts as twice the
  shares it bought against a price that has been halved. The two
  cancel, and the position holds its value across the event.

  Concretely: 100 shares bought at R$ 50 in 2020, split 1:2 in 2022.
  `adjusted_close` for 2020 is ~R$ 25. Valuing 100 shares there gives
  R$ 2.500 for a position that was worth R$ 5.000; valuing the restated
  200 gives R$ 5.000. In this convention a split is a **no-op** — which
  is why the index restates the flows and then walks them unchanged,
  instead of applying the ratio as an event.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum
from app.domain.portfolio.service import ShareAdjustment, replay_timeline
from app.quant.returns import PricePoint

#: Scales an as-traded share count for one asset on one day.
#:
#: The seam between the two conventions above: `performance_index` hands
#: in a restatement onto today's shares, and `value_series` hands in
#: nothing at all.
ShareFactor = Callable[[int, date], Decimal]

#: Starting level of the unit series.
#:
#: Cancels out of every derived quantity, as in `benchmarks.series`. 100
#: keeps a level readable as a percentage of the start.
DEFAULT_BASE = Decimal(100)

ZERO = Decimal(0)


@dataclass(frozen=True)
class ValuePoint:
    """What the holdings were worth on one date, and what they cost.

    `value` is priced at the **raw close** — what the market printed —
    because "how much do I have" is a point-in-time question. `invested`
    is the money that had gone into holdings by that date, cumulative and
    net of sales.

    The gap between them is the part that is not the investor's own
    money. Drawing them together is what stops a wealth curve being read
    as performance: a line that doubled because R$ 1.000 arrived every
    month looks identical to one that doubled on returns until the second
    line is under it.
    """

    date: date
    value: Decimal
    invested: Decimal


def value_series(
    transactions: list[Transaction],
    closes: dict[int, dict[date, Decimal]],
    as_of: date | None = None,
    adjustments: Sequence[ShareAdjustment] = (),
) -> list[ValuePoint]:
    """The portfolio's worth over time, oldest first.

    ⚠️ **`closes` must be raw closes**, from
    `market_data.series.closes_by_asset` — not the adjusted map
    `performance_index` takes. Feeding adjusted prices here would report
    a past patrimônio far below what the investor actually held, because
    adjustment scales old closes down by every dividend since.

    Deliberately a separate walk from `performance_index` rather than a
    second output of it. The two answer different questions from
    different prices, and computing them together would put both kinds of
    price inside one calculation — which is the error this module's
    docstring exists to prevent.

    A date where any held asset has no stored price is skipped entirely,
    the same rule `performance_index` follows: a total missing one
    holding is not a smaller patrimônio, it is a different portfolio.

    Nothing after `as_of` is read (rule 108).
    """
    ordered = sorted(
        transactions, key=lambda tx: (tx.transaction_date.date(), tx.id or 0)
    )
    if not ordered:
        return []

    flows_by_date = _external_flows(ordered)
    # Forward convention: the ratio applies from its ex-date on, because
    # the raw close is quoted in the shares of its own day.
    quantities_by_date = _quantities_after_each_day(ordered, adjustments)
    valuation_dates = _valuation_dates(closes, ordered[0], as_of)
    ledger_days = sorted(set(flows_by_date) | set(quantities_by_date))

    points: list[ValuePoint] = []
    held: dict[int, Decimal] = {}
    invested = ZERO
    next_ledger_day = 0

    for day in valuation_dates:
        while (
            next_ledger_day < len(ledger_days) and ledger_days[next_ledger_day] <= day
        ):
            ledger_day = ledger_days[next_ledger_day]
            invested += flows_by_date.get(ledger_day, ZERO)
            held = quantities_by_date.get(ledger_day, held)
            next_ledger_day += 1

        value = _value_on(held, closes, day)
        if value is None:
            continue

        points.append(ValuePoint(date=day, value=value, invested=invested))

    return points


def performance_index(
    transactions: list[Transaction],
    prices: dict[int, dict[date, Decimal]],
    as_of: date | None = None,
    base: Decimal = DEFAULT_BASE,
    adjustments: Sequence[ShareAdjustment] = (),
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

    # Final-share convention: every quantity is restated onto today's
    # share count, the same terms `adjusted_close` is quoted in, and a
    # split then needs no event of its own (see the module docstring).
    restate = _final_share_factor(adjustments)
    flows_by_date = _external_share_flows(ordered, restate)
    quantities_by_date = _quantities_after_each_day(ordered, factor=restate)

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
    pending_shares: dict[int, Decimal] = {}
    held: dict[int, Decimal] = {}
    next_ledger_day = 0

    for day in valuation_dates:
        while (
            next_ledger_day < len(ledger_days) and ledger_days[next_ledger_day] <= day
        ):
            ledger_day = ledger_days[next_ledger_day]
            for asset_id, shares in flows_by_date.get(ledger_day, {}).items():
                pending_shares[asset_id] = pending_shares.get(asset_id, ZERO) + shares
            held = quantities_by_date.get(ledger_day, held)
            next_ledger_day += 1

        value = _value_on(held, prices, day)
        if value is None:
            # Not valuable today; the flow waits for a date that is.
            continue

        flow = _flow_value(pending_shares, prices, day)
        if flow is None:
            # The flow itself cannot be valued today — an asset sold out
            # entirely has no price obligation left. Skipping keeps it
            # pending; neutralising it with a zero would read the sale as
            # a loss of the whole position.
            continue

        if previous_value is not None and previous_value > 0:
            level *= (value - flow) / previous_value

        points.append(PricePoint(date=day, adjusted_close=level))
        previous_value = value
        pending_shares = {}

    return points


# -- helpers ---------------------------------------------------------


def _external_share_flows(
    ordered: list[Transaction],
    factor: ShareFactor | None = None,
) -> dict[date, dict[int, Decimal]]:
    """Holdings entering or leaving, **in shares**, by date and asset.

    Shares rather than cash, because the flow is subtracted from a value
    measured at `adjusted_close` and the two must be the same currency —
    see the module docstring. The caller multiplies by the adjusted close
    of the day it settles the flow on.

    Fees become share-equivalents at the price of their own transaction:
    R$ 5 on shares bought at R$ 10 is half a share of money that went out
    and never became value. A transaction priced at zero contributes no
    fee term rather than dividing by it — there is no exchange rate
    between cash and shares to convert with.
    """
    flows: dict[date, dict[int, Decimal]] = {}
    for tx in ordered:
        if tx.asset_id is None:
            continue
        fee_shares = tx.fees / tx.price if tx.price > 0 else ZERO
        if tx.type is TransactionTypeEnum.BUY:
            shares = tx.quantity + fee_shares
        elif tx.type is TransactionTypeEnum.SELL:
            shares = -tx.quantity + fee_shares
        else:
            # DEPOSIT / WITHDRAWAL never touch holdings; DIVIDEND is
            # already inside `adjusted_close` (see the module docstring).
            continue
        day = tx.transaction_date.date()
        if factor is not None:
            shares *= factor(tx.asset_id, day)
        by_asset = flows.setdefault(day, {})
        by_asset[tx.asset_id] = by_asset.get(tx.asset_id, ZERO) + shares
    return flows


def _flow_value(
    pending: dict[int, Decimal],
    prices: dict[int, dict[date, Decimal]],
    day: date,
) -> Decimal | None:
    """What the pending flows are worth at `day`'s adjusted closes.

    `None` when any asset with a pending flow has no price for the day,
    which is the same rule `_value_on` follows and for the same reason: a
    flow valued at part of itself is not a smaller correction, it is the
    wrong one.
    """
    total = ZERO
    for asset_id, shares in pending.items():
        if shares == 0:
            continue
        price = prices.get(asset_id, {}).get(day)
        if price is None:
            return None
        total += shares * price
    return total


def _external_flows(ordered: list[Transaction]) -> dict[date, Decimal]:
    """Net money entering the tracked holdings, by date, in BRL.

    Cash, unlike `_external_share_flows`: this one feeds `value_series`,
    where the holdings are valued at the raw close and the investor's own
    money is exactly the quantity being drawn. Fees are part of it on both
    sides — they leave the investor's pocket and never become value.
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
    adjustments: Sequence[ShareAdjustment] = (),
    factor: ShareFactor | None = None,
) -> dict[date, dict[int, Decimal]]:
    """Holdings as they stood at the end of each day the ledger moved.

    Only days with activity get an entry; the callers carry the last
    known holdings forward across quiet days. A share action counts as
    activity: the day a split lands, the holding changed even though
    nobody traded, and a snapshot has to say so.

    The two conventions of the module docstring are the two arguments,
    and they are mutually exclusive by construction:

    - `adjustments` applies each ratio **forward**, from its ex-date on,
      which is what a raw-close valuation needs.
    - `factor` restates every quantity onto **today's** share count,
      which is what an adjusted-close valuation needs — and in those
      terms a split changes nothing, so no event is applied.
    """
    snapshots: dict[date, dict[int, Decimal]] = {}
    running: dict[int, Decimal] = {}

    for event in replay_timeline(ordered, adjustments):
        if isinstance(event, ShareAdjustment):
            held = running.get(event.asset_id, ZERO)
            if held > ZERO and event.ratio > ZERO:
                running[event.asset_id] = held * event.ratio
                snapshots[event.ex_date] = dict(running)
            continue

        tx = event
        if tx.asset_id is not None:
            day = tx.transaction_date.date()
            quantity = tx.quantity
            if factor is not None:
                quantity *= factor(tx.asset_id, day)
            if tx.type is TransactionTypeEnum.BUY:
                running[tx.asset_id] = running.get(tx.asset_id, ZERO) + quantity
            elif tx.type is TransactionTypeEnum.SELL:
                # Never let the ledger drive a holding negative, matching
                # `compute_positions`: this stays a safe derivation of
                # whatever ledger it is handed.
                remaining = running.get(tx.asset_id, ZERO) - quantity
                running[tx.asset_id] = max(remaining, ZERO)
        snapshots[tx.transaction_date.date()] = dict(running)

    return snapshots


def _final_share_factor(adjustments: Sequence[ShareAdjustment]) -> ShareFactor:
    """The factor restating an as-traded share count into today's shares.

    Every ratio that went ex **after** the trade, multiplied together. A
    trade made after the last action restates by 1, which is why the
    recent end of a series is untouched — and why an empty `adjustments`
    reproduces the pre-W13-001 behaviour exactly.
    """
    by_asset: dict[int, list[ShareAdjustment]] = {}
    for adjustment in adjustments:
        if adjustment.ratio > ZERO:
            by_asset.setdefault(adjustment.asset_id, []).append(adjustment)

    def factor(asset_id: int, day: date) -> Decimal:
        product = Decimal(1)
        for adjustment in by_asset.get(asset_id, ()):
            if adjustment.ex_date > day:
                product *= adjustment.ratio
        return product

    return factor


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
