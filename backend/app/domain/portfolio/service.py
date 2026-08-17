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
"""

from dataclasses import dataclass, field
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum

ZERO = Decimal(0)


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


def compute_positions(transactions: list[Transaction]) -> dict[int, AssetPosition]:
    """Derive current per-asset positions from a portfolio's transactions.

    Returns a mapping of asset_id -> AssetPosition, including assets whose
    position was fully closed (quantity == 0) but still have a non-zero
    realized P&L or dividends, so that historical outcome is not silently
    dropped. Assets with no BUY/SELL/DIVIDEND activity are omitted.
    """
    positions: dict[int, AssetPosition] = {}

    asset_transactions = [t for t in transactions if t.asset_id is not None]
    for tx in sorted(asset_transactions, key=_sort_key):
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


def compute_asset_quantity(transactions: list[Transaction], asset_id: int) -> Decimal:
    """Convenience accessor for a single asset's currently held quantity."""
    position = compute_positions(transactions).get(asset_id)
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
