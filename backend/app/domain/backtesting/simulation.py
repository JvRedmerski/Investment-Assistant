"""Replaying a strategy over history, one session at a time.

Pure and free of I/O (rule 68): prices, corporate actions and the
strategy all arrive as arguments, so this module can be tested with
known inputs and known outputs and cannot accidentally read a database
row from the future.

## The order of a session, and why look-ahead cannot get in

Rule 58 is the critical one here, and its own example is exactly the
trap a naive backtest falls into: using a session's close to decide a
trade *in* that session. Two properties of the walk below rule it out.

1. **A decision sees one session and never the next.** The strategy is
   handed a `SimulationState` carrying the day, the cash, the positions
   and the closes **of that session**. It is not handed the price map,
   the calendar or anything it could index forward with.

2. **An order decided on a session fills on the following one.** You can
   read a close only after it has printed, so an order placed on it is
   an order for tomorrow. Filling it at the same close would be
   assuming a price nobody could have traded at, which is the
   look-ahead rule 58 names — and the difference is not academic, since
   the gap between deciding and filling is exactly where a real
   investor's slippage lives.

Each session therefore runs in this order:

    cash actions → fills pending from yesterday → contribution → decision

Dividends first, so money that arrived today can be spent today. Fills
before the contribution, so the strategy sees the positions it actually
holds when it decides.

## Two prices, never mixed

Everything here executes and values at the **raw close** — what the
market printed — and dividends arrive separately, as cash. That is the
investor's world, and it is the only combination that does not double
count: `adjusted_close` already contains every dividend, so crediting
cash on top of it would pay the investor twice. The mirror of the unit
error W11-002 corrected, avoided by construction rather than by care.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum
from app.domain.backtesting.schemas import (
    ZERO,
    CostModel,
    Decision,
    Fill,
    Order,
    Side,
    Simulation,
    SimulationState,
    Strategy,
    whole_shares,
)
from app.domain.portfolio.service import ShareAdjustment, compute_positions


@dataclass(frozen=True)
class CashAction:
    """A payout, in reais per share, on the session it went ex."""

    asset_id: int
    ex_date: date
    amount_per_share: Decimal
    label: str = ""


@dataclass(frozen=True)
class ContributionSchedule:
    """How much arrives, and when.

    `day_of_month` is a target rather than a date: markets do not open
    on every 5th, so the contribution lands on the first session **on or
    after** it. A month whose target falls past its last session
    contributes on that last session rather than being skipped, because
    money that arrived is money that arrived.
    """

    amount: Decimal
    day_of_month: int = 1


#: Named so a fill that did not happen says why, rather than vanishing.
NO_PRICE = "NO_PRICE"
BELOW_ONE_SHARE = "BELOW_ONE_SHARE"
INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
NOTHING_HELD = "NOTHING_HELD"


def contribution_sessions(
    calendar: Sequence[date], schedule: ContributionSchedule
) -> list[date]:
    """The session each month's contribution actually lands on."""
    chosen: list[date] = []
    seen: set[tuple[int, int]] = set()
    for day in calendar:
        key = (day.year, day.month)
        if key in seen:
            continue
        if day.day >= schedule.day_of_month:
            seen.add(key)
            chosen.append(day)
    # A month whose target day never arrives (the calendar ends first)
    # still contributes, on the last session it has.
    months = {(day.year, day.month) for day in calendar}
    for year, month in sorted(months - seen):
        sessions = [d for d in calendar if (d.year, d.month) == (year, month)]
        if sessions:
            chosen.append(sessions[-1])
    return sorted(chosen)


def simulate(
    *,
    start: date,
    end: date,
    schedule: ContributionSchedule,
    strategy: Strategy,
    closes: Mapping[int, Mapping[date, Decimal]],
    cash_actions: Sequence[CashAction] = (),
    share_actions: Sequence[ShareAdjustment] = (),
    costs: CostModel = CostModel(),
) -> Simulation:
    """Replay `strategy` from `start` to `end` and report what happened.

    `closes` are **raw** closes by asset by date — the price that
    printed, never the adjusted one (see the module docstring). The
    trading calendar is every date any of them knows about, so an asset
    with no stored price simply never trades rather than trading at a
    fabricated one (rule 44).
    """
    calendar = sorted(
        {day for by_date in closes.values() for day in by_date if start <= day <= end}
    )
    if not calendar:
        return Simulation(transactions=(), adjustments=tuple(share_actions))

    payouts: dict[date, list[CashAction]] = {}
    for action in cash_actions:
        if start <= action.ex_date <= end and action.amount_per_share > ZERO:
            payouts.setdefault(action.ex_date, []).append(action)

    contribution_days = set(contribution_sessions(calendar, schedule))

    transactions: list[Transaction] = []
    decisions: list[Decision] = []
    cash_by_date: dict[date, Decimal] = {}
    pending: list[Order] = []
    cash = ZERO
    contributed = ZERO
    fees_paid = ZERO
    dividends_received = ZERO

    for day in calendar:
        # 1. Payouts on holdings as they stood at the open of the session.
        for action in payouts.get(day, ()):
            held = _held(transactions, share_actions, day, action.asset_id)
            if held <= ZERO:
                continue
            amount = held * action.amount_per_share
            transactions.append(
                _transaction(
                    len(transactions) + 1,
                    TransactionTypeEnum.DIVIDEND,
                    action.asset_id,
                    held,
                    action.amount_per_share,
                    ZERO,
                    day,
                )
            )
            cash += amount
            dividends_received += amount

        # 2. Yesterday's orders, filled at today's close.
        if pending:
            fills, cash, fees = _execute(
                pending, day, closes, transactions, share_actions, cash, costs
            )
            fees_paid += fees
            if decisions:
                decisions[-1] = Decision(
                    day=decisions[-1].day,
                    cash_before=decisions[-1].cash_before,
                    orders=decisions[-1].orders,
                    fills=tuple(fills),
                    closes=decisions[-1].closes,
                )
            pending = []

        # 3. The contribution, then the decision it pays for.
        if day in contribution_days:
            cash += schedule.amount
            contributed += schedule.amount
            transactions.append(
                _transaction(
                    len(transactions) + 1,
                    TransactionTypeEnum.DEPOSIT,
                    None,
                    schedule.amount,
                    Decimal(1),
                    ZERO,
                    day,
                )
            )
            state = SimulationState(
                day=day,
                cash=cash,
                positions=compute_positions(
                    transactions, _applicable(share_actions, day)
                ),
                closes={
                    asset_id: by_date[day]
                    for asset_id, by_date in closes.items()
                    if day in by_date
                },
            )
            orders = list(strategy(state))
            decisions.append(
                Decision(
                    day=day,
                    cash_before=cash,
                    orders=tuple(orders),
                    fills=(),
                    closes=dict(state.closes),
                )
            )
            pending = orders

        cash_by_date[day] = cash

    return Simulation(
        transactions=tuple(transactions),
        adjustments=tuple(_applicable(share_actions, end)),
        cash_by_date=cash_by_date,
        decisions=tuple(decisions),
        contributed=contributed,
        fees_paid=fees_paid,
        dividends_received=dividends_received,
    )


# -- helpers ---------------------------------------------------------


def _applicable(
    share_actions: Sequence[ShareAdjustment], day: date
) -> list[ShareAdjustment]:
    """Only the actions that had already gone ex (rule 108)."""
    return [action for action in share_actions if action.ex_date <= day]


def _held(
    transactions: Sequence[Transaction],
    share_actions: Sequence[ShareAdjustment],
    day: date,
    asset_id: int,
) -> Decimal:
    """The quantity in custody for one asset, as of `day`.

    Derived through `compute_positions` rather than tracked alongside it,
    so the simulation and the rest of the project can never disagree on
    what a ledger means — including how a share action changes it
    (W13-001).
    """
    positions = compute_positions(list(transactions), _applicable(share_actions, day))
    position = positions.get(asset_id)
    return position.quantity if position is not None else ZERO


def _transaction(
    id_: int,
    type_: TransactionTypeEnum,
    asset_id: int | None,
    quantity: Decimal,
    price: Decimal,
    fees: Decimal,
    day: date,
) -> Transaction:
    """One row of the simulated ledger, detached from any session.

    Never added to a database: a backtest is derived, like positions and
    plans, and storing one would make it a fact rather than a
    calculation (rule 16).
    """
    return Transaction(
        id=id_,
        portfolio_id=0,
        asset_id=asset_id,
        type=type_,
        quantity=quantity,
        price=price,
        fees=fees,
        transaction_date=datetime.combine(day, time.min, tzinfo=UTC),
    )


def _execute(
    orders: Sequence[Order],
    day: date,
    closes: Mapping[int, Mapping[date, Decimal]],
    transactions: list[Transaction],
    share_actions: Sequence[ShareAdjustment],
    cash: Decimal,
    costs: CostModel,
) -> tuple[list[Fill], Decimal, Decimal]:
    """Fill what can be filled at today's close, and name what cannot."""
    fills: list[Fill] = []
    fees_paid = ZERO

    for order in orders:
        price = closes.get(order.asset_id, {}).get(day)
        if price is None or price <= ZERO:
            fills.append(_missed(order, day, NO_PRICE))
            continue

        if order.side is Side.BUY:
            quantity = whole_shares(order.amount, price)
            # The price moved between the decision and the fill, which is
            # the whole reason those are different sessions. Shrink to
            # what the money now buys rather than overdrawing.
            while quantity > ZERO and (
                quantity * price + costs.charge(quantity * price) > cash
            ):
                quantity -= 1
            if quantity <= ZERO:
                reason = BELOW_ONE_SHARE if order.amount < price else INSUFFICIENT_CASH
                fills.append(_missed(order, day, reason))
                continue

            notional = quantity * price
            fees = costs.charge(notional)
            cash -= notional + fees
        else:
            held = _held(transactions, share_actions, day, order.asset_id)
            quantity = min(whole_shares(order.amount, price), held)
            if quantity <= ZERO:
                fills.append(_missed(order, day, NOTHING_HELD))
                continue
            notional = quantity * price
            fees = costs.charge(notional)
            cash += notional - fees

        fees_paid += fees
        transactions.append(
            _transaction(
                len(transactions) + 1,
                (
                    TransactionTypeEnum.BUY
                    if order.side is Side.BUY
                    else TransactionTypeEnum.SELL
                ),
                order.asset_id,
                quantity,
                price,
                fees,
                day,
            )
        )
        fills.append(
            Fill(
                day=day,
                asset_id=order.asset_id,
                ticker=order.ticker,
                side=order.side,
                quantity=quantity,
                price=price,
                fees=fees,
            )
        )

    return fills, cash, fees_paid


def _missed(order: Order, day: date, reason: str) -> Fill:
    return Fill(
        day=day,
        asset_id=order.asset_id,
        ticker=order.ticker,
        side=order.side,
        quantity=ZERO,
        price=ZERO,
        fees=ZERO,
        reason=reason,
    )
