"""Portfolio positions engine.

Positions are never stored independently of the transaction ledger
(AGENTS.md rule 16: "Evitar armazenar simultaneamente quantity/average_price
como valores independentes sem mecanismo de consistência"). This module
derives them deterministically from `Transaction` rows every time they are
needed, using the moving-average (weighted-average) cost method:

- BUY increases quantity and folds the trade cost (quantity * price + fees)
  into the weighted average cost of the position.
- SELL decreases quantity; the average cost of the *remaining* shares is
  unchanged (moving-average method), and realizes P&L for the shares sold
  (proceeds minus fees, minus the cost basis of the shares sold).
- DIVIDEND does not change quantity or average cost; it accumulates as cash
  received for that asset.
- DEPOSIT/WITHDRAWAL are portfolio-level cash flows (no asset_id) and do not
  affect any asset's position; see `compute_net_contributions`.

No market data is used here — current market value is out of scope until
the Market Data integration (Wave 05) provides prices. Only cost-basis
figures (invested amount, average cost, realized P&L, dividends) are
computed.

## The ledger is not the whole story: share actions (W13-001)

A split, a reverse split or a bonus issue changes how many shares sit in
custody **without producing a transaction**. The investor did nothing, so
the ledger records nothing, and a position replayed from the ledger alone
keeps the pre-event count for ever.

That was harmless while positions were cost-basis only — a split changes
neither what was paid nor the realized result. It stopped being harmless
when market value arrived (W11-001), because `quantity × price` is wrong
by the whole factor: Magazine Luiza's 1:10 reverse split would leave a
holding valued at ten times what it is worth.

So the replay takes the share actions alongside the ledger and applies
them to whatever is open on the ex-date. `invested_amount` and
`realized_pnl` do **not** move — no money changed hands — while
`quantity` scales by the ratio and `average_price` by its inverse, which
is the only pair of changes that keeps cost basis intact.

An action applies **before** any transaction dated on the same ex-date:
a purchase made on the ex-date already buys post-event shares at the
post-event price, so scaling it again would double-count the event.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum

ZERO = Decimal(0)


@dataclass(frozen=True)
class ShareAdjustment:
    """A ratio the market applied to a holding, on the session it applied.

    `ratio` is **new shares per old share**, the same convention
    `corporate_actions.share_ratio` stores and `market_data.adjustment`
    reads: a 1:2 split is `2`, a 1:10 reverse split is `0.1`. Inverting
    it produces a position that is wrong by the square of the factor and
    still looks like a number, which is why the convention is stated in
    both modules rather than inferred at either.

    `label` is carried for the audit trail — a position that changed
    without a transaction should be able to say what changed it.
    """

    asset_id: int
    ex_date: date
    ratio: Decimal
    label: str = ""


@dataclass
class AssetPosition:
    asset_id: int
    quantity: Decimal = ZERO
    average_price: Decimal = ZERO
    invested_amount: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    dividends_received: Decimal = field(default=ZERO)


def _sort_key(transaction: Transaction) -> tuple:
    # Chronological order, with id as a tiebreaker for same-timestamp
    # transactions, so replaying the ledger never uses information from a
    # transaction that had not "happened yet" relative to another
    # (AGENTS.md rule 58 — no look-ahead, applied to bookkeeping order too).
    return (transaction.transaction_date, transaction.id or 0)


def replay_timeline(
    transactions: list[Transaction],
    adjustments: Sequence[ShareAdjustment] = (),
) -> list[Transaction | ShareAdjustment]:
    """Transactions and share actions in the order they actually happened.

    A share action sorts **before** the transactions of its own ex-date,
    because a trade made on the ex-date is already dealing in post-event
    shares. The ledger's existing intra-day order (`_sort_key`) is
    preserved, so this is a strict refinement of the previous replay
    rather than a reordering of it.

    Shared with `portfolio.performance`: the two modules have to walk the
    same events in the same order or they describe two portfolios.
    """
    ordered = sorted(transactions, key=_sort_key)
    events: list[tuple[date, int, int, Transaction | ShareAdjustment]] = [
        (adjustment.ex_date, 0, index, adjustment)
        for index, adjustment in enumerate(adjustments)
    ]
    events += [
        (tx.transaction_date.date(), 1, index, tx) for index, tx in enumerate(ordered)
    ]
    events.sort(key=lambda event: event[:3])
    return [event[3] for event in events]


def _apply_share_adjustment(
    positions: dict[int, AssetPosition], adjustment: ShareAdjustment
) -> None:
    """Scale an open holding by a share action, leaving cost basis alone.

    Nothing happens to a position that is not open: an action cannot
    create shares out of a holding that does not exist, and applying one
    to a closed position would resurrect it.
    """
    position = positions.get(adjustment.asset_id)
    if position is None or position.quantity <= ZERO or adjustment.ratio <= ZERO:
        return
    position.quantity *= adjustment.ratio
    position.average_price /= adjustment.ratio


def compute_positions(
    transactions: list[Transaction],
    adjustments: Sequence[ShareAdjustment] = (),
) -> dict[int, AssetPosition]:
    """Derive current per-asset positions from a portfolio's transactions.

    Returns a mapping of asset_id -> AssetPosition, including assets whose
    position was fully closed (quantity == 0) but still have a non-zero
    realized P&L or dividends, so that historical outcome is not silently
    dropped. Assets with no BUY/SELL/DIVIDEND activity are omitted.

    `adjustments` are the share actions that moved a holding without a
    transaction (see the module docstring). Omitted, the replay is what
    it was before W13-001 — which is correct only for a ledger whose
    assets never split.
    """
    positions: dict[int, AssetPosition] = {}

    asset_transactions = [t for t in transactions if t.asset_id is not None]
    for event in replay_timeline(asset_transactions, adjustments):
        if isinstance(event, ShareAdjustment):
            _apply_share_adjustment(positions, event)
            continue

        tx = event
        position = positions.setdefault(
            tx.asset_id, AssetPosition(asset_id=tx.asset_id)
        )

        if tx.type == TransactionTypeEnum.BUY:
            trade_cost = tx.quantity * tx.price + tx.fees
            new_quantity = position.quantity + tx.quantity
            position.invested_amount += trade_cost
            position.quantity = new_quantity
            position.average_price = (
                position.invested_amount / new_quantity if new_quantity > 0 else ZERO
            )

        elif tx.type == TransactionTypeEnum.SELL:
            # Never let a sell push quantity negative even if the caller did
            # not pre-validate against the held quantity: this function must
            # stay a safe, pure derivation of whatever ledger it is given.
            sell_quantity = min(tx.quantity, position.quantity)
            cost_of_sold = position.average_price * sell_quantity
            proceeds = tx.quantity * tx.price - tx.fees
            position.realized_pnl += proceeds - cost_of_sold
            position.quantity -= sell_quantity
            position.invested_amount -= cost_of_sold
            if position.quantity <= 0:
                position.quantity = ZERO
                position.invested_amount = ZERO
                position.average_price = ZERO

        elif tx.type == TransactionTypeEnum.DIVIDEND:
            position.dividends_received += tx.quantity * tx.price

    return {
        asset_id: position
        for asset_id, position in positions.items()
        if position.quantity > ZERO
        or position.realized_pnl != ZERO
        or position.dividends_received != ZERO
    }


def compute_asset_quantity(
    transactions: list[Transaction],
    asset_id: int,
    adjustments: Sequence[ShareAdjustment] = (),
) -> Decimal:
    """Convenience accessor for a single asset's currently held quantity."""
    position = compute_positions(transactions, adjustments).get(asset_id)
    return position.quantity if position is not None else ZERO


def compute_net_contributions(transactions: list[Transaction]) -> Decimal:
    """Total cash contributed to the portfolio: sum(DEPOSIT) - sum(WITHDRAWAL)."""
    total = ZERO
    for tx in transactions:
        amount = tx.quantity * tx.price
        if tx.type == TransactionTypeEnum.DEPOSIT:
            total += amount
        elif tx.type == TransactionTypeEnum.WITHDRAWAL:
            total -= amount
    return total
