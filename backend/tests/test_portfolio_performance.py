"""Tests for the time-weighted portfolio performance index.

Pure function, hand-computed expectations. No database, no HTTP.

The example is kept deliberately small — one asset, round numbers — so
every expected level below can be checked in your head, which is the only
way an error in the *test* would be caught.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum
from app.domain.portfolio.performance import performance_index
from app.quant.returns import total_return

ASSET = 1
OTHER = 2


def _tx(
    day: int,
    kind: TransactionTypeEnum,
    quantity="0",
    price="0",
    fees="0",
    asset_id=ASSET,
    tx_id=None,
) -> Transaction:
    return Transaction(
        id=tx_id if tx_id is not None else day,
        portfolio_id=1,
        asset_id=asset_id,
        type=kind,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fees=Decimal(fees),
        transaction_date=datetime(2026, 1, day, tzinfo=UTC),
    )


def _prices(*pairs, asset_id=ASSET) -> dict[int, dict[date, Decimal]]:
    return {asset_id: {date(2026, 1, day): Decimal(price) for day, price in pairs}}


def _levels(points) -> list[Decimal]:
    return [point.adjusted_close for point in points]


def test_the_index_tracks_the_price_of_a_single_untouched_holding():
    """10 shares bought at 10, price 10 -> 11 -> 12: the index is +20%."""
    transactions = [_tx(1, TransactionTypeEnum.BUY, "10", "10")]
    prices = _prices((1, "10"), (2, "11"), (3, "12"))

    points = performance_index(transactions, prices)

    assert [point.date for point in points] == [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
    ]
    assert _levels(points) == [Decimal(100), Decimal(110), Decimal(120)]


def test_a_contribution_does_not_move_the_index():
    """The whole point of time-weighting, in one comparison.

    Same prices as above, but 10 more shares are bought on day 2 at 11.
    The portfolio's value doubles; the index is identical, because
    nothing about the investor's decision to add money is performance.
    """
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10", tx_id=1),
        _tx(2, TransactionTypeEnum.BUY, "10", "11", tx_id=2),
    ]
    prices = _prices((1, "10"), (2, "11"), (3, "12"))

    points = performance_index(transactions, prices)

    assert _levels(points) == [Decimal(100), Decimal(110), Decimal(120)]


def test_a_sale_at_the_market_price_does_not_move_the_index():
    """Selling is a decision about size, not a result."""
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10", tx_id=1),
        _tx(2, TransactionTypeEnum.SELL, "5", "10", tx_id=2),
    ]
    prices = _prices((1, "10"), (2, "10"), (3, "11"))

    points = performance_index(transactions, prices)

    # Day 2: value 50, flow -50, so (50 + 50) / 100 = 1.0 -> still 100.
    # Day 3: 5 shares at 11 = 55, against 50 -> 100 * 1.1 = 110.
    assert _levels(points) == [Decimal(100), Decimal(100), Decimal(110)]


def test_fees_show_up_as_a_loss_because_they_never_become_value():
    """R$ 5 of fees on a R$ 100 portfolio is a 5% drag.

    Day 2: 10 more shares at an unchanged price of 10, plus 5 in fees.
    Value 200, flow 105, so (200 - 105) / 100 = 0.95.
    """
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10", tx_id=1),
        _tx(2, TransactionTypeEnum.BUY, "10", "10", fees="5", tx_id=2),
    ]
    prices = _prices((1, "10"), (2, "10"))

    points = performance_index(transactions, prices)

    assert _levels(points) == [Decimal(100), Decimal(95)]


def test_deposits_and_withdrawals_are_invisible_to_the_index():
    """They move cash the index never values."""
    with_cash = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10", tx_id=1),
        _tx(2, TransactionTypeEnum.DEPOSIT, "1", "1000", asset_id=None, tx_id=2),
        _tx(2, TransactionTypeEnum.WITHDRAWAL, "1", "500", asset_id=None, tx_id=3),
    ]
    without = [_tx(1, TransactionTypeEnum.BUY, "10", "10", tx_id=1)]
    prices = _prices((1, "10"), (2, "12"))

    assert _levels(performance_index(with_cash, prices)) == _levels(
        performance_index(without, prices)
    )


def test_a_dividend_is_not_counted_because_it_is_already_in_the_adjusted_close():
    """Counting it here would credit the same cash twice."""
    with_dividend = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10", tx_id=1),
        _tx(2, TransactionTypeEnum.DIVIDEND, "10", "0.5", tx_id=2),
    ]
    without = [_tx(1, TransactionTypeEnum.BUY, "10", "10", tx_id=1)]
    prices = _prices((1, "10"), (2, "12"))

    assert _levels(performance_index(with_dividend, prices)) == _levels(
        performance_index(without, prices)
    )


def test_two_assets_are_valued_together():
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10", asset_id=ASSET, tx_id=1),
        _tx(1, TransactionTypeEnum.BUY, "10", "10", asset_id=OTHER, tx_id=2),
    ]
    prices = {
        ASSET: {date(2026, 1, 1): Decimal(10), date(2026, 1, 2): Decimal(12)},
        OTHER: {date(2026, 1, 1): Decimal(10), date(2026, 1, 2): Decimal(8)},
    }

    points = performance_index(transactions, prices)

    # 200 -> 120 + 80 = 200: the two moves cancel exactly.
    assert _levels(points) == [Decimal(100), Decimal(100)]


def test_a_date_missing_a_price_for_a_held_asset_is_not_valued():
    """A partial total is a different portfolio, not a rounder answer."""
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10", asset_id=ASSET, tx_id=1),
        _tx(1, TransactionTypeEnum.BUY, "10", "10", asset_id=OTHER, tx_id=2),
    ]
    prices = {
        ASSET: {
            date(2026, 1, 1): Decimal(10),
            date(2026, 1, 2): Decimal(12),
            date(2026, 1, 3): Decimal(12),
        },
        # OTHER has no price on the 2nd.
        OTHER: {date(2026, 1, 1): Decimal(10), date(2026, 1, 3): Decimal(10)},
    }

    points = performance_index(transactions, prices)

    assert [point.date for point in points] == [date(2026, 1, 1), date(2026, 1, 3)]


def test_a_purchase_during_a_price_gap_is_still_neutralised():
    """The flow waits for a date that can be valued, and is exact there.

    Without the carry-forward the day-2 purchase would be measured as a
    gain. With it, the sub-period runs 1 -> 3 and the flow is settled at
    day 3's price: 10 shares at 12, so (240 - 120) / 100 = 1.20.

    That 120 is the *true* time-weighted answer, not an approximation of
    it. Splitting at the flow gives (10*P2 / 100) * (240 / 20*P2), and
    the unknown day-2 price cancels — the new shares are the same asset
    as the old ones, so it moves both halves together. Buying an asset
    the portfolio did not already hold is the case that stays
    approximate.
    """
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10", tx_id=1),
        _tx(2, TransactionTypeEnum.BUY, "10", "11", tx_id=2),
    ]
    prices = _prices((1, "10"), (3, "12"))  # nothing on the 2nd

    points = performance_index(transactions, prices)

    assert _levels(points) == [Decimal(100), Decimal(120)]


def test_the_index_is_unchanged_by_the_adjustment_factor():
    """The unit error the real database caught, pinned at minimum size.

    Identical trades and an identical +10% return. With an adjustment
    factor of 1 the traded price and the adjusted close coincide, which
    is the only case the rest of this file exercises. With a factor of 3
    -- an asset that has paid years of dividends -- subtracting the cash
    spent instead of the value added drove the level to -100.
    """
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "100", "10", tx_id=1),
        _tx(2, TransactionTypeEnum.BUY, "100", "10", tx_id=2),
    ]

    unadjusted = performance_index(
        transactions, _prices((1, "10"), (2, "10"), (3, "11"))
    )
    adjusted = performance_index(transactions, _prices((1, "3"), (2, "3"), (3, "3.3")))

    assert _levels(unadjusted) == [Decimal(100), Decimal(100), Decimal(110)]
    assert _levels(adjusted) == [Decimal(100), Decimal(100), Decimal(110)]


def test_a_sale_priced_away_from_the_adjusted_close_is_still_neutralised():
    """The same unit rule on the way out.

    Half the position sold at a traded price of 30 while the adjusted
    close is 10: the index must see 10 shares leaving, not R$ 300.
    """
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "20", "30", tx_id=1),
        _tx(2, TransactionTypeEnum.SELL, "10", "30", tx_id=2),
    ]
    prices = _prices((1, "10"), (2, "10"), (3, "11"))

    points = performance_index(transactions, prices)

    assert _levels(points) == [Decimal(100), Decimal(100), Decimal(110)]


def test_nothing_before_the_first_transaction_is_measured():
    transactions = [_tx(5, TransactionTypeEnum.BUY, "10", "10")]
    prices = _prices((1, "9"), (5, "10"), (6, "11"))

    points = performance_index(transactions, prices)

    assert [point.date for point in points] == [date(2026, 1, 5), date(2026, 1, 6)]


def test_nothing_after_as_of_is_read():
    transactions = [_tx(1, TransactionTypeEnum.BUY, "10", "10")]
    prices = _prices((1, "10"), (2, "11"), (3, "12"))

    points = performance_index(transactions, prices, as_of=date(2026, 1, 2))

    assert [point.date for point in points] == [date(2026, 1, 1), date(2026, 1, 2)]


def test_a_fully_sold_portfolio_earns_nothing_while_it_holds_nothing():
    """No division by zero, and no invented return for money in cash."""
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "10", "10", tx_id=1),
        _tx(2, TransactionTypeEnum.SELL, "10", "12", tx_id=2),
        _tx(4, TransactionTypeEnum.BUY, "10", "12", tx_id=3),
    ]
    prices = _prices((1, "10"), (2, "12"), (3, "20"), (4, "12"), (5, "15"))

    points = performance_index(transactions, prices)

    # Day 2: sold at the market price, so still 120 / 100 -> 120.
    # Day 3: holding nothing, value 0 and the level is flat.
    # Day 4: repurchased; the sub-period opened at 0, so no return.
    # Day 5: 12 -> 15 is +25% on the level standing at 120.
    assert _levels(points) == [
        Decimal(100),
        Decimal(120),
        Decimal(120),
        Decimal(120),
        Decimal(150),
    ]


def test_a_portfolio_with_no_transactions_has_no_index():
    assert performance_index([], _prices((1, "10"))) == []


def test_a_portfolio_with_no_stored_prices_has_no_index():
    assert performance_index([_tx(1, TransactionTypeEnum.BUY, "10", "10")], {}) == []


def test_the_index_feeds_the_quant_engine_without_an_adapter():
    """It is a `PricePoint` series, so `total_return` just reads it."""
    transactions = [_tx(1, TransactionTypeEnum.BUY, "10", "10")]
    prices = _prices((1, "10"), (2, "11"), (3, "12"))

    measured = total_return(performance_index(transactions, prices))

    assert measured is not None
    assert measured.value == Decimal("0.2")
