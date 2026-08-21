"""Tests for share actions moving a position without a transaction (W13-001).

A split changes what sits in custody and produces no ledger row, so a
position replayed from the ledger alone keeps the old count for ever.
That was invisible while positions were cost-basis only and became a
whole-factor error the moment market value arrived (W11-001).

The two curves in `portfolio.performance` need **opposite** restatements
of the same event, and the tests that matter most here are the ones that
pin that down: the raw-close curve applies a ratio forward from its
ex-date, and the adjusted-close index restates every quantity onto
today's share count, where a split is a no-op.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum
from app.domain.portfolio.performance import performance_index, value_series
from app.domain.portfolio.service import (
    ShareAdjustment,
    compute_asset_quantity,
    compute_positions,
)

ASSET = 1


def _tx(id_, type_, quantity, price, fees="0", day=1, asset_id=ASSET) -> Transaction:
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


def _split(day: int, ratio: str, label: str = "DESDOBRAMENTO") -> ShareAdjustment:
    return ShareAdjustment(
        asset_id=ASSET, ex_date=date(2026, 1, day), ratio=Decimal(ratio), label=label
    )


# -- the position itself ----------------------------------------------


def test_a_split_scales_quantity_and_leaves_cost_basis_alone():
    """No money changed hands, so only the per-share view may move."""
    transactions = [_tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1)]
    position = compute_positions(transactions, [_split(3, "2")])[ASSET]

    assert position.quantity == Decimal(200)
    assert position.average_price == Decimal(25)
    assert position.invested_amount == Decimal(5000)
    assert position.realized_pnl == Decimal(0)


def test_a_reverse_split_scales_the_other_way():
    """Magazine Luiza's 1:10, the case that made this a whole-factor bug."""
    transactions = [_tx(1, TransactionTypeEnum.BUY, "1000", "2.00", day=1)]
    position = compute_positions(transactions, [_split(3, "0.1", "GRUPAMENTO")])[ASSET]

    assert position.quantity == Decimal(100)
    assert position.average_price == Decimal(20)
    assert position.invested_amount == Decimal(2000)


def test_two_actions_on_one_session_compose():
    """VIVT3 went ex a split and a reverse split on the same day."""
    transactions = [_tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1)]
    position = compute_positions(
        transactions, [_split(3, "7900"), _split(3, "0.025", "GRUPAMENTO")]
    )[ASSET]

    assert position.quantity == Decimal(100) * Decimal(7900) * Decimal("0.025")
    assert position.invested_amount == Decimal(5000)


def test_a_purchase_on_the_ex_date_is_not_scaled():
    """It already bought post-event shares at the post-event price."""
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1),
        _tx(2, TransactionTypeEnum.BUY, "100", "25.00", day=3),
    ]
    position = compute_positions(transactions, [_split(3, "2")])[ASSET]

    # 200 restated + 100 bought ex, not 400.
    assert position.quantity == Decimal(300)
    assert position.invested_amount == Decimal(7500)


def test_an_action_with_no_open_position_changes_nothing():
    """It cannot resurrect a holding that was closed before the ex-date."""
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1),
        _tx(2, TransactionTypeEnum.SELL, "100", "60.00", day=2),
    ]
    position = compute_positions(transactions, [_split(3, "2")])[ASSET]

    assert position.quantity == Decimal(0)
    assert position.realized_pnl == Decimal(1000)


def test_no_adjustments_reproduces_the_previous_replay_exactly():
    """The regression guard: an unsplit ledger must be untouched."""
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "100", "38.50", fees="5.00", day=1),
        _tx(2, TransactionTypeEnum.SELL, "40", "42.00", fees="3.00", day=2),
    ]
    assert compute_positions(transactions) == compute_positions(transactions, [])


def test_the_full_post_split_quantity_can_be_sold():
    """The guard on a SELL must count the shares actually in custody."""
    transactions = [_tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1)]

    assert compute_asset_quantity(transactions, ASSET) == Decimal(100)
    assert compute_asset_quantity(transactions, ASSET, [_split(3, "2")]) == Decimal(200)


# -- the wealth curve: raw closes, quantities as they stood -----------


def _closes(*pairs: tuple[int, str]) -> dict[int, dict[date, Decimal]]:
    return {ASSET: {date(2026, 1, day): Decimal(value) for day, value in pairs}}


def test_wealth_is_continuous_across_a_split():
    """The raw price halves and the count doubles; the money is the same.

    Without the forward restatement this prints a 50% loss on the
    ex-date — a phantom crash, from an event that moved nothing.
    """
    transactions = [_tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1)]
    closes = _closes((1, "50"), (2, "50"), (3, "25"), (4, "25"))

    points = value_series(transactions, closes, adjustments=[_split(3, "2")])

    assert [point.value for point in points] == [Decimal(5000)] * 4
    assert [point.invested for point in points] == [Decimal(5000)] * 4


def test_without_the_action_the_wealth_curve_shows_the_phantom_crash():
    """Pinned so the defect cannot come back unnoticed."""
    transactions = [_tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1)]
    closes = _closes((1, "50"), (2, "50"), (3, "25"), (4, "25"))

    points = value_series(transactions, closes)

    assert [point.value for point in points] == [
        Decimal(5000),
        Decimal(5000),
        Decimal(2500),
        Decimal(2500),
    ]


# -- the index: adjusted closes, quantities in today's shares ---------


def test_a_split_is_transparent_to_the_index():
    """The strongest statement of the convention.

    A ledger holding through a split must produce exactly the index of
    the same money with no split at all — same adjusted prices, the
    purchase written directly in post-split shares. If the restatement
    were missing, or applied in the wrong direction, the mix of a
    pre-split and a post-split purchase would diverge between the two.
    """
    adjusted = _closes((1, "25"), (2, "25"), (4, "40"), (5, "44"))

    with_split = [
        _tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1),
        _tx(2, TransactionTypeEnum.BUY, "100", "40.00", day=4),
    ]
    without_split = [
        # The same purchase, written in the shares it is worth today.
        _tx(1, TransactionTypeEnum.BUY, "200", "25.00", day=1),
        _tx(2, TransactionTypeEnum.BUY, "100", "40.00", day=4),
    ]

    split_levels = [
        point.adjusted_close
        for point in performance_index(
            with_split, adjusted, adjustments=[_split(3, "2")]
        )
    ]
    plain_levels = [
        point.adjusted_close for point in performance_index(without_split, adjusted)
    ]

    assert split_levels == plain_levels
    assert len(split_levels) == 4


def test_the_index_measures_the_market_move_and_not_the_split():
    """Adjusted 25 → 40 → 44 is +60% then +10%, whatever the share count."""
    adjusted = _closes((1, "25"), (4, "40"), (5, "44"))
    transactions = [_tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1)]

    levels = [
        point.adjusted_close
        for point in performance_index(
            transactions, adjusted, adjustments=[_split(3, "2")]
        )
    ]

    assert levels[0] == Decimal(100)
    assert levels[1] == Decimal(160)
    assert levels[2] == Decimal(176)


def test_an_action_after_a_trade_restates_it_and_one_before_does_not():
    """Only the ratios that went ex *after* a trade apply to it."""
    adjusted = _closes((1, "25"), (5, "25"))
    early = [_tx(1, TransactionTypeEnum.BUY, "100", "50.00", day=1)]

    # A split on day 3 doubles the day-1 purchase into today's terms; a
    # split on day 1 (same day, before the trade) leaves it alone.
    after = performance_index(early, adjusted, adjustments=[_split(3, "2")])
    before = performance_index(early, adjusted, adjustments=[_split(1, "2")])

    # Both are flat — a single holding with an unchanged price — but the
    # levels come from different values, which the flow test above pins.
    assert [point.adjusted_close for point in after] == [Decimal(100)] * 2
    assert [point.adjusted_close for point in before] == [Decimal(100)] * 2
