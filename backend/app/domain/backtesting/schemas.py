"""What a simulation is told, and what it reports back.

Provider-agnostic and I/O-free, like `app.quant`: nothing here reads a
database or knows which strategy is being tested.

## The simulation speaks in ledger

Its output is a list of `Transaction` rows — the same shape a real
portfolio is recorded in — plus the share actions that moved a holding
without one. That is deliberate and it is most of the design: it means
`compute_positions`, `value_series` and `performance_index` measure a
backtest with **exactly** the code that measures the investor's own
portfolio. A second valuation path would be a second set of bugs, and
the first divergence between them would show up as a backtest that
disagrees with the dashboard for reasons nobody could name.
"""

import enum
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_UP, Decimal

from app.data.models.portfolio import Transaction
from app.domain.portfolio.service import AssetPosition, ShareAdjustment

ZERO = Decimal(0)
CENTAVO = Decimal("0.01")

#: B3's cash-equity fees for a retail investor, as a fraction of volume:
#: the negotiation fee plus the settlement fee.
#:
#: A default, not a fact about the reader's broker — every run may
#: override it, and `CostModel` is echoed back with the result so a
#: figure can always be read next to the costs that produced it. Rule 62
#: asks that costs be modelled rather than assumed away; assuming a
#: *precise* number would be the opposite error, so this one is stated as
#: the approximation it is.
B3_TRADING_FEE_RATE = Decimal("0.0003")


class Side(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class CostModel:
    """What a trade costs, beyond the price of the shares.

    `brokerage` is per order and `brokerage_rate` proportional, because
    both shapes exist in the market and a backtest run under one says
    nothing about the other. Zero brokerage is the honest default for
    the Brazilian retail broker this project is written for, and it is
    still a *choice* the result carries with it.
    """

    brokerage: Decimal = ZERO
    brokerage_rate: Decimal = ZERO
    exchange_rate: Decimal = B3_TRADING_FEE_RATE

    def charge(self, notional: Decimal) -> Decimal:
        """The fee on a trade of `notional` reais, rounded to the centavo.

        Rounded **up**, because a fee that lands between centavos is not
        one the investor gets to keep the fraction of, and a backtest
        that rounds costs down flatters itself a little on every trade.
        """
        raw = self.brokerage + notional * (self.brokerage_rate + self.exchange_rate)
        return raw.quantize(CENTAVO, rounding=ROUND_UP)


@dataclass(frozen=True)
class Order:
    """An instruction the strategy produced, in reais rather than shares.

    Reais because that is what the allocator decides in: the contribution
    is money, and how many shares it buys is a fact about the price on
    the execution session, which the strategy is not allowed to know yet.
    """

    asset_id: int
    ticker: str
    side: Side
    amount: Decimal


@dataclass(frozen=True)
class Fill:
    """What actually happened to an order, and why, when it did not.

    A backtest that silently drops an unfillable order reports a
    strategy nobody ran. Every order ends as a fill with a `quantity` of
    zero and a named `reason`, the same standard `AllocationPlan` holds
    its skipped candidates to.
    """

    day: date
    asset_id: int
    ticker: str
    side: Side
    quantity: Decimal
    price: Decimal
    fees: Decimal
    reason: str = ""


@dataclass(frozen=True)
class Decision:
    """One contribution date: what the strategy saw and what it ordered.

    Kept for the audit trail (rule 112). A backtest result that cannot
    say *when* it decided what is not reproducible in any useful sense —
    it is a number with a story attached.
    """

    day: date
    cash_before: Decimal
    orders: tuple[Order, ...]
    fills: tuple[Fill, ...]


@dataclass(frozen=True)
class SimulationState:
    """Everything the strategy is allowed to know, on one date.

    The whole no-look-ahead guarantee of the engine is the shape of this
    object: it carries the day, the money, the positions as they stand
    and the closes **of that session and no later**. A strategy cannot
    read a future price because it is never handed one (rules 58/108).
    """

    day: date
    cash: Decimal
    positions: Mapping[int, AssetPosition]
    closes: Mapping[int, Decimal]


#: Decides what to buy, given only what was knowable on the day.
Strategy = Callable[[SimulationState], list[Order]]


@dataclass(frozen=True)
class Simulation:
    """The replay, as a ledger plus the cash the ledger cannot hold.

    `cash_by_date` exists because the transaction ledger models holdings
    and contributions but has nowhere to put an idle balance — the
    unallocated remainder of a contribution, or a dividend waiting for
    the next one. Leaving it out would understate the portfolio by
    exactly the money the strategy chose not to spend, which is a real
    result and not an absence.
    """

    transactions: tuple[Transaction, ...]
    adjustments: tuple[ShareAdjustment, ...]
    cash_by_date: dict[date, Decimal] = field(default_factory=dict)
    decisions: tuple[Decision, ...] = ()
    contributed: Decimal = ZERO
    fees_paid: Decimal = ZERO
    dividends_received: Decimal = ZERO

    def cash_on(self, day: date) -> Decimal:
        """The balance at the end of `day`, carried forward across quiet days."""
        best = ZERO
        for when, amount in sorted(self.cash_by_date.items()):
            if when > day:
                break
            best = amount
        return best


def whole_shares(amount: Decimal, price: Decimal) -> Decimal:
    """How many whole shares `amount` buys at `price`.

    Whole, because nobody buys 3.7 shares: B3's fractional market trades
    in single shares and not in slices of one. The remainder is not lost
    — it stays as cash and reaches the next contribution — but pretending
    it bought a fraction would make every minimum-ticket rule in the
    allocator meaningless and flatter small portfolios in particular.
    """
    if price <= ZERO:
        return ZERO
    return (amount / price).quantize(Decimal(1), rounding=ROUND_DOWN)
