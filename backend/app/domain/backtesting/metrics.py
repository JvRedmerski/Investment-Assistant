"""What a replay is worth measuring for, beyond the curve it drew.

Pure and I/O-free (rule 68): everything here reads a finished
`Simulation` and nothing else.

The series figures — total return, CAGR, volatility, drawdown, Sharpe,
Sortino, beta, alpha — are **not** here. They are `quant` and
`benchmarks.comparison`, measuring the backtest's own time-weighted
index with exactly the code that measures the investor's portfolio
(`backtesting.service` wires that up). Re-deriving them for a backtest
would be the second valuation path W13-002 exists to avoid.

What is here is the half of rule 63 a price series cannot answer: how
many trades there were, what they cost, and how the closed ones turned
out.

## Two costs, and only one of them is an assumption

**Fees** are modelled: `CostModel` states a rate and the result carries
it, so a figure can be read next to the costs that produced it (rule
107).

**Slippage is measured.** The engine decides on one session's close and
fills on the next one's, because a close can only be read after it has
printed. The gap between those two prices is what the delay cost, on
these days, in this run — so it is summed from what actually happened
rather than assumed at some basis-point rate. A backtest that invents a
slippage constant is reporting an assumption as a result.

The sign convention is the investor's: **positive means it cost money.**
A buy filled above the price the strategy saw is positive, a sale filled
below it is positive, and a favourable gap is negative. Averaging the
two would hide that a run was lucky in one direction and unlucky in the
other, so both totals are reported.

## A trade is closed by a sale, and this project does not sell

`win_rate`, `average_win`, `average_loss`, `profit_factor` and
`expectancy` (rules 63/64) are all defined on **closed** trades. The
strategy under test never sells — closing a weight gap by dilution
rather than by selling is the whole of ADR-028 — so on the project's own
strategy every one of them comes back `None`, with `closed_trades` at
zero saying why.

That is the honest answer rather than a missing feature. They are
computed anyway, because the module is written against the engine and
not against one strategy, and because Wave 19 backtests setups that do
close. A strategy that never closes a trade has no win rate; reporting
`0%` there would read as *every trade lost*.

## Realized results come from the position engine, not from a formula

The result of a sale depends on the moving average cost at the moment it
happened, which `compute_positions` already derives. So each sale's
result is read as the **change** in that position's `realized_pnl`
across the sale, rather than recomputed from a second average-cost
implementation that could drift from the first.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum
from app.domain.backtesting.simulation import ZERO, Decision, Fill, Side, Simulation
from app.domain.portfolio.service import ShareAdjustment, compute_positions


@dataclass(frozen=True)
class ClosedTrade:
    """One sale, and what it realized after costs.

    `result` is proceeds net of fees less the average cost of what was
    sold — the same quantity `AssetPosition.realized_pnl` accumulates,
    read one sale at a time.
    """

    asset_id: int
    day: date
    quantity: Decimal
    price: Decimal
    result: Decimal


@dataclass(frozen=True)
class TradeStatistics:
    """The execution side of a backtest (rules 63, 64 and 107).

    Every ratio is `None` rather than zero when there is nothing to
    measure it on, the same rule the score engine and the quant engine
    follow (ADR-014). `closed_trades` is what distinguishes "no wins" from
    "nothing closed yet".
    """

    trades: int
    buys: int
    sells: int
    closed_trades: int
    wins: int
    losses: int
    win_rate: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    profit_factor: Decimal | None
    expectancy: Decimal | None
    realized_result: Decimal
    fees: Decimal
    #: Measured, not assumed — see the module docstring. Positive is a cost.
    slippage: Decimal
    slippage_paid: Decimal
    slippage_earned: Decimal
    dividends_received: Decimal
    contributed: Decimal
    #: How many orders ended unfilled, by the reason that stopped them.
    unfilled: dict[str, int]


def trade_statistics(run: Simulation) -> TradeStatistics:
    """Measure `run`'s execution, without touching its price series."""
    fills = [fill for decision in run.decisions for fill in decision.fills]
    filled = [fill for fill in fills if fill.quantity > ZERO]

    closed = closed_trades(run.transactions, run.adjustments)
    wins = [trade.result for trade in closed if trade.result > ZERO]
    losses = [trade.result for trade in closed if trade.result < ZERO]

    average_win = _mean(wins)
    average_loss = _mean([-value for value in losses])
    win_rate = Decimal(len(wins)) / len(closed) if closed else None

    paid, earned = _slippage(run.decisions)

    return TradeStatistics(
        trades=len(filled),
        buys=sum(1 for fill in filled if fill.side is Side.BUY),
        sells=sum(1 for fill in filled if fill.side is Side.SELL),
        closed_trades=len(closed),
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        average_win=average_win,
        average_loss=average_loss,
        profit_factor=_profit_factor(wins, losses),
        expectancy=_expectancy(win_rate, average_win, average_loss),
        realized_result=sum((trade.result for trade in closed), ZERO),
        fees=run.fees_paid,
        slippage=paid + earned,
        slippage_paid=paid,
        slippage_earned=earned,
        dividends_received=run.dividends_received,
        contributed=run.contributed,
        unfilled=_unfilled(fills),
    )


def closed_trades(
    transactions: Sequence[Transaction],
    adjustments: Sequence[ShareAdjustment] = (),
) -> list[ClosedTrade]:
    """Every sale in the ledger, with what it realized.

    Read as the change in the position's `realized_pnl` across each sale,
    so this agrees with `compute_positions` by construction rather than
    by care — including on the share actions that restate a holding
    (W13-001), which is why they are replayed here too.

    Quadratic in the number of transactions, and deliberately so: a
    backtest runs a few hundred of them, and the alternative is a second
    average-cost implementation that can disagree with the first. If a
    profile ever shows this mattering, the fix is an incremental replay in
    `portfolio.service`, shared by both callers — not a copy here.
    """
    ordered = sorted(
        transactions, key=lambda tx: (tx.transaction_date.date(), tx.id or 0)
    )

    trades: list[ClosedTrade] = []
    for index, transaction in enumerate(ordered):
        if transaction.type is not TransactionTypeEnum.SELL:
            continue
        asset_id = transaction.asset_id
        if asset_id is None:
            continue

        day = transaction.transaction_date.date()
        before = _realized(ordered[:index], adjustments, asset_id, day)
        after = _realized(ordered[: index + 1], adjustments, asset_id, day)
        trades.append(
            ClosedTrade(
                asset_id=asset_id,
                day=day,
                quantity=transaction.quantity,
                price=transaction.price,
                result=after - before,
            )
        )
    return trades


# -- helpers ---------------------------------------------------------


def _realized(
    transactions: Sequence[Transaction],
    adjustments: Sequence[ShareAdjustment],
    asset_id: int,
    day: date,
) -> Decimal:
    """One asset's cumulative realized result over a ledger prefix."""
    applicable = [adjustment for adjustment in adjustments if adjustment.ex_date <= day]
    position = compute_positions(list(transactions), applicable).get(asset_id)
    return position.realized_pnl if position is not None else ZERO


def _slippage(decisions: Sequence[Decision]) -> tuple[Decimal, Decimal]:
    """What the decide-then-fill gap cost, and what it gave back.

    Returned as two totals rather than one net figure: a run that paid
    R$ 40 on some fills and gained R$ 38 on others is not the same as one
    that barely moved, and netting them to R$ 2 would say it was.
    """
    paid = ZERO
    earned = ZERO
    for decision in decisions:
        for fill in decision.fills:
            cost = _fill_slippage(fill, decision)
            if cost is None:
                continue
            if cost > ZERO:
                paid += cost
            else:
                earned += cost
    return paid, earned


def _fill_slippage(fill: Fill, decision: Decision) -> Decimal | None:
    """What this fill cost against the price its decision saw.

    `None` when the strategy never saw a price for the asset — it decided
    without one, so there is no gap to attribute a cost to.
    """
    if fill.quantity <= ZERO:
        return None
    seen = decision.closes.get(fill.asset_id)
    if seen is None or seen <= ZERO:
        return None

    difference = fill.price - seen
    if fill.side is Side.SELL:
        difference = -difference
    return fill.quantity * difference


def _unfilled(fills: Sequence[Fill]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for fill in fills:
        if fill.quantity <= ZERO and fill.reason:
            counts[fill.reason] = counts.get(fill.reason, 0) + 1
    return counts


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, ZERO) / len(values)


def _profit_factor(
    wins: Sequence[Decimal], losses: Sequence[Decimal]
) -> Decimal | None:
    """Gross profit over gross loss.

    `None` with no losses rather than infinity: a sample that never lost
    carries no evidence about how much it loses, the same reading
    `sortino` takes of a sample with no downside.
    """
    gross_loss = -sum(losses, ZERO)
    if gross_loss <= ZERO:
        return None
    return sum(wins, ZERO) / gross_loss


def _expectancy(
    win_rate: Decimal | None,
    average_win: Decimal | None,
    average_loss: Decimal | None,
) -> Decimal | None:
    """`(win_rate * average_win) - (loss_rate * average_loss)` (rule 64).

    In reais per closed trade. A strategy can win under half its trades
    and still be positive, which is exactly what this figure is for and
    what a win rate alone hides.

    A side with no trades contributes nothing rather than blocking the
    figure: a run of three wins and no losses has an expectancy, and it
    is the average win.
    """
    if win_rate is None:
        return None
    gain = (average_win or ZERO) * win_rate
    loss = (average_loss or ZERO) * (Decimal(1) - win_rate)
    return gain - loss
