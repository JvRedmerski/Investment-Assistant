"""Unit tests for the positions engine (AGENTS.md rule 68: known-input ->
known-output cases, not just "does not crash").

Transaction rows are constructed as plain in-memory objects (no DB session
needed): `compute_positions` only reads their attributes.
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum
from app.domain.portfolio.service import (
    ZERO,
    compute_asset_quantity,
    compute_net_contributions,
    compute_positions,
)

ASSET_A = 1
ASSET_B = 2


def _tx(
    id_,
    type_,
    quantity,
    price,
    fees="0",
    asset_id=ASSET_A,
    day=1,
) -> Transaction:
    return Transaction(
        id=id_,
        portfolio_id=1,
        asset_id=asset_id,
        type=type_,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fees=Decimal(fees),
        transaction_date=datetime(2026, 1, day, tzinfo=UTC),
    )


def test_single_buy_sets_quantity_and_average_price():
    transactions = [_tx(1, TransactionTypeEnum.BUY, "100", "38.50", fees="5.00", day=1)]

    positions = compute_positions(transactions)

    position = positions[ASSET_A]
    assert position.quantity == Decimal(100)
    assert position.invested_amount == Decimal("3855.00")
    assert position.average_price == Decimal("38.55")
    assert position.realized_pnl == ZERO
    assert position.dividends_received == ZERO


def test_multiple_buys_produce_weighted_average_price():
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10.00", day=1),
        _tx(2, TransactionTypeEnum.BUY, "10", "20.00", day=2),
    ]

    position = compute_positions(transactions)[ASSET_A]

    assert position.quantity == Decimal(20)
    assert position.invested_amount == Decimal("300.00")
    assert position.average_price == Decimal("15.00")


def test_partial_sell_keeps_average_price_and_realizes_pnl():
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10.00", day=1),
        _tx(2, TransactionTypeEnum.BUY, "10", "20.00", day=2),
        _tx(3, TransactionTypeEnum.SELL, "5", "18.00", day=3),
    ]

    position = compute_positions(transactions)[ASSET_A]

    # Cost of the 5 sold shares = 5 * average_price(15) = 75
    # Proceeds = 5 * 18 = 90 -> realized P&L = 15
    assert position.quantity == Decimal(15)
    assert position.average_price == Decimal("15.00")
    assert position.invested_amount == Decimal("225.00")
    assert position.realized_pnl == Decimal("15.00")


def test_full_sell_closes_position_but_keeps_realized_pnl():
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10.00", day=1),
        _tx(2, TransactionTypeEnum.BUY, "10", "20.00", day=2),
        _tx(3, TransactionTypeEnum.SELL, "5", "18.00", day=3),
        _tx(4, TransactionTypeEnum.SELL, "15", "20.00", day=4),
    ]

    position = compute_positions(transactions)[ASSET_A]

    assert position.quantity == ZERO
    assert position.invested_amount == ZERO
    assert position.average_price == ZERO
    # First sell realized 15.00, second sells 15 units at cost 15.00 each
    # (225 cost) for proceeds of 300 -> realizes 75.00. Total: 90.00.
    assert position.realized_pnl == Decimal("90.00")


def test_dividend_accumulates_without_changing_quantity_or_average_price():
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10.00", day=1),
        _tx(2, TransactionTypeEnum.DIVIDEND, "10", "1.50", day=2),
    ]

    position = compute_positions(transactions)[ASSET_A]

    assert position.quantity == Decimal(10)
    assert position.average_price == Decimal("10.00")
    assert position.dividends_received == Decimal("15.00")


def test_positions_are_independent_per_asset():
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10.00", asset_id=ASSET_A, day=1),
        _tx(2, TransactionTypeEnum.BUY, "5", "50.00", asset_id=ASSET_B, day=1),
    ]

    positions = compute_positions(transactions)

    assert positions[ASSET_A].quantity == Decimal(10)
    assert positions[ASSET_B].quantity == Decimal(5)
    assert positions[ASSET_B].average_price == Decimal("50.00")


def test_out_of_order_input_is_replayed_chronologically():
    # SELL appears first in the list, but its transaction_date is *after*
    # both buys, so replay order must follow the date, not list order.
    transactions = [
        _tx(3, TransactionTypeEnum.SELL, "5", "18.00", day=3),
        _tx(1, TransactionTypeEnum.BUY, "10", "10.00", day=1),
        _tx(2, TransactionTypeEnum.BUY, "10", "20.00", day=2),
    ]

    position = compute_positions(transactions)[ASSET_A]

    assert position.quantity == Decimal(15)
    assert position.realized_pnl == Decimal("15.00")


def test_closed_position_with_no_pnl_or_dividends_is_omitted():
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10.00", day=1),
        _tx(2, TransactionTypeEnum.SELL, "10", "10.00", day=2),
    ]

    positions = compute_positions(transactions)

    assert ASSET_A not in positions


def test_compute_asset_quantity_returns_zero_for_unknown_asset():
    assert compute_asset_quantity([], asset_id=999) == ZERO


def test_compute_net_contributions_nets_deposits_and_withdrawals():
    transactions = [
        Transaction(
            id=1,
            portfolio_id=1,
            asset_id=None,
            type=TransactionTypeEnum.DEPOSIT,
            quantity=Decimal(1000),
            price=Decimal(1),
            fees=Decimal(0),
            transaction_date=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        Transaction(
            id=2,
            portfolio_id=1,
            asset_id=None,
            type=TransactionTypeEnum.WITHDRAWAL,
            quantity=Decimal(200),
            price=Decimal(1),
            fees=Decimal(0),
            transaction_date=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    ]

    assert compute_net_contributions(transactions) == Decimal(800)
