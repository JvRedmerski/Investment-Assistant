"""Tests for the execution side of a backtest (W13-004).

Hand-computed throughout (rule 68). The two that carry the most weight
are the ones about *absence*: a strategy that never sells has no win
rate, and saying so is not the same as saying it lost every trade.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum
from app.domain.backtesting.metrics import closed_trades, trade_statistics
from app.domain.backtesting.simulation import (
    INSUFFICIENT_CASH,
    NO_PRICE,
    ContributionSchedule,
    CostModel,
    Decision,
    Fill,
    Order,
    Side,
    Simulation,
    simulate,
)
from app.domain.portfolio.service import ShareAdjustment

AAA = 1
BBB = 2
ZERO = Decimal(0)
FREE = CostModel(exchange_rate=ZERO)


def _tx(
    id_: int,
    type_: TransactionTypeEnum,
    day: int,
    quantity: str,
    price: str,
    fees: str = "0",
    asset_id: int = AAA,
) -> Transaction:
    return Transaction(
        id=id_,
        portfolio_id=0,
        asset_id=asset_id,
        type=type_,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fees=Decimal(fees),
        transaction_date=datetime.combine(date(2026, 1, day), time.min, tzinfo=UTC),
    )


def _buy(id_: int, day: int, quantity: str, price: str, **kwargs) -> Transaction:
    return _tx(id_, TransactionTypeEnum.BUY, day, quantity, price, **kwargs)


def _sell(id_: int, day: int, quantity: str, price: str, **kwargs) -> Transaction:
    return _tx(id_, TransactionTypeEnum.SELL, day, quantity, price, **kwargs)


def _fill(
    day: int, quantity: str, price: str, side: Side = Side.BUY, asset_id: int = AAA
) -> Fill:
    return Fill(
        day=date(2026, 1, day),
        asset_id=asset_id,
        ticker="AAA",
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fees=ZERO,
    )


def _decision(day: int, closes: dict[int, str], *fills: Fill) -> Decision:
    return Decision(
        day=date(2026, 1, day),
        cash_before=Decimal(1000),
        orders=(
            Order(asset_id=AAA, ticker="AAA", side=Side.BUY, amount=Decimal(1000)),
        ),
        fills=fills,
        closes={asset_id: Decimal(price) for asset_id, price in closes.items()},
    )


# -- what a sale realized ---------------------------------------------


def test_a_sale_realizes_proceeds_less_the_average_cost():
    """100 at R$ 10 bought, 40 sold at R$ 15: 40 x 5 = R$ 200."""
    ledger = [_buy(1, 5, "100", "10"), _sell(2, 9, "40", "15")]

    trades = closed_trades(ledger)

    assert [trade.result for trade in trades] == [Decimal(200)]
    assert trades[0].day == date(2026, 1, 9)


def test_the_cost_of_what_was_sold_is_the_moving_average():
    """100 at R$ 10 and 100 at R$ 20 average R$ 15; 50 sold at R$ 25 makes 500."""
    ledger = [
        _buy(1, 5, "100", "10"),
        _buy(2, 6, "100", "20"),
        _sell(3, 9, "50", "25"),
    ]

    assert [trade.result for trade in closed_trades(ledger)] == [Decimal(500)]


def test_fees_on_both_sides_come_out_of_the_realized_result():
    """Cost basis 100 x 10 + 3 = 1003, average 10.03. Sale of 100 at 15
    nets 1500 - 4 = 1496, so the result is 1496 - 1003 = 493."""
    ledger = [
        _buy(1, 5, "100", "10", fees="3"),
        _sell(2, 9, "100", "15", fees="4"),
    ]

    assert [trade.result for trade in closed_trades(ledger)] == [Decimal(493)]


def test_a_split_between_the_buy_and_the_sale_does_not_move_the_result():
    """Twice the shares at half the average is the same money.

    100 at R$ 10 becomes 200 at R$ 5 across a 1:2 split. Selling all 200
    at R$ 7,50 realizes 1500 - 1000 = R$ 500 — identical to selling 100
    at R$ 15 without the split, because a split changes the share count
    and not the value (W13-001).
    """
    ledger = [_buy(1, 5, "100", "10"), _sell(2, 9, "200", "7.50")]
    split = ShareAdjustment(
        asset_id=AAA, ex_date=date(2026, 1, 7), ratio=Decimal(2), label="DESDOBRAMENTO"
    )

    assert [trade.result for trade in closed_trades(ledger, [split])] == [Decimal(500)]


def test_a_ledger_that_never_sells_closes_no_trade():
    ledger = [_buy(1, 5, "100", "10"), _buy(2, 6, "100", "12")]

    assert closed_trades(ledger) == []


def test_a_deposit_is_not_a_trade():
    ledger = [
        _tx(1, TransactionTypeEnum.DEPOSIT, 5, "1000", "1", asset_id=None),
        _buy(2, 6, "100", "10"),
    ]

    assert closed_trades(ledger) == []


# -- the statistics ---------------------------------------------------


def _run(transactions=(), decisions=(), **kwargs) -> Simulation:
    return Simulation(
        transactions=tuple(transactions),
        adjustments=tuple(kwargs.pop("adjustments", ())),
        decisions=tuple(decisions),
        **kwargs,
    )


def test_a_strategy_that_never_sells_has_no_win_rate_rather_than_a_zero_one():
    """Zero would read as *every trade lost*. There were no closed trades.

    This is the state the project's own strategy is always in: closing a
    weight gap by dilution rather than by selling is ADR-028.
    """
    run = _run(
        transactions=[_buy(1, 5, "100", "10")],
        decisions=[_decision(5, {AAA: "10"}, _fill(6, "100", "10"))],
    )

    stats = trade_statistics(run)

    assert stats.trades == 1
    assert stats.buys == 1
    assert stats.sells == 0
    assert stats.closed_trades == 0
    assert stats.win_rate is None
    assert stats.average_win is None
    assert stats.average_loss is None
    assert stats.profit_factor is None
    assert stats.expectancy is None
    assert stats.realized_result == ZERO


def test_expectancy_is_positive_under_a_win_rate_below_one_half():
    """Rule 64's own point, in numbers.

    Two wins of R$ 100 and three losses of R$ 50: win rate 2/5, so
    expectancy is (0,4 x 100) - (0,6 x 50) = 40 - 30 = R$ 10 a trade,
    positive on a 40% win rate. Profit factor is 200/150 = 4/3.
    """
    ledger = [_buy(1, 1, "500", "10")]
    for index in range(2):
        # +R$ 100: 100 shares at 10 sold at 11.
        ledger.append(_sell(len(ledger) + 1, 2 + index, "100", "11"))
    for index in range(3):
        # -R$ 50: 100 shares at 10 sold at 9.50.
        ledger.append(_sell(len(ledger) + 1, 4 + index, "100", "9.50"))

    stats = trade_statistics(_run(transactions=ledger))

    assert stats.closed_trades == 5
    assert stats.wins == 2
    assert stats.losses == 3
    assert stats.win_rate == Decimal(2) / Decimal(5)
    assert stats.average_win == Decimal(100)
    assert stats.average_loss == Decimal(50)
    assert stats.profit_factor == Decimal(200) / Decimal(150)
    assert stats.expectancy == Decimal(10)
    assert stats.realized_result == Decimal(50)


def test_profit_factor_is_absent_rather_than_infinite_without_a_loss():
    """A sample that never lost says nothing about how much it loses."""
    ledger = [_buy(1, 1, "200", "10"), _sell(2, 2, "100", "11")]

    stats = trade_statistics(_run(transactions=ledger))

    assert stats.profit_factor is None
    assert stats.expectancy == Decimal(100)


# -- slippage, measured -----------------------------------------------


def test_slippage_is_what_the_gap_between_deciding_and_filling_cost():
    """Decided against R$ 10, filled at R$ 10,20: 100 shares cost R$ 20."""
    run = _run(decisions=[_decision(5, {AAA: "10"}, _fill(6, "100", "10.20"))])

    stats = trade_statistics(run)

    assert stats.slippage_paid == Decimal(20)
    assert stats.slippage_earned == ZERO
    assert stats.slippage == Decimal(20)


def test_a_favourable_gap_is_reported_separately_from_an_unfavourable_one():
    """Netting R$ 20 paid against R$ 15 earned would report R$ 5 of drift.

    A run that moved in both directions is not a run that barely moved,
    and both totals are what says which happened.
    """
    run = _run(
        decisions=[
            _decision(5, {AAA: "10"}, _fill(6, "100", "10.20")),
            _decision(7, {AAA: "10"}, _fill(8, "100", "9.85")),
        ]
    )

    stats = trade_statistics(run)

    assert stats.slippage_paid == Decimal(20)
    assert stats.slippage_earned == Decimal(-15)
    assert stats.slippage == Decimal(5)


def test_a_sale_filled_below_the_price_it_saw_is_a_cost_too():
    """The sign is the investor's: selling into a fall cost money."""
    run = _run(
        decisions=[_decision(5, {AAA: "10"}, _fill(6, "100", "9.50", side=Side.SELL))]
    )

    assert trade_statistics(run).slippage_paid == Decimal(50)


def test_an_order_decided_without_a_price_has_no_gap_to_charge():
    run = _run(decisions=[_decision(5, {BBB: "10"}, _fill(6, "100", "10.20"))])

    stats = trade_statistics(run)

    assert stats.slippage == ZERO


# -- what did not happen ----------------------------------------------


def test_unfilled_orders_are_counted_by_the_reason_that_stopped_them():
    run = _run(
        decisions=[
            Decision(
                day=date(2026, 1, 5),
                cash_before=Decimal(1000),
                orders=(),
                fills=(
                    Fill(
                        day=date(2026, 1, 6),
                        asset_id=AAA,
                        ticker="AAA",
                        side=Side.BUY,
                        quantity=ZERO,
                        price=ZERO,
                        fees=ZERO,
                        reason=NO_PRICE,
                    ),
                    Fill(
                        day=date(2026, 1, 6),
                        asset_id=BBB,
                        ticker="BBB",
                        side=Side.BUY,
                        quantity=ZERO,
                        price=ZERO,
                        fees=ZERO,
                        reason=INSUFFICIENT_CASH,
                    ),
                ),
                closes={AAA: Decimal(10)},
            )
        ]
    )

    stats = trade_statistics(run)

    assert stats.unfilled == {NO_PRICE: 1, INSUFFICIENT_CASH: 1}
    assert stats.trades == 0


# -- against a real replay --------------------------------------------


def test_the_statistics_read_a_run_the_engine_actually_produced():
    """End to end on the engine, so the two agree about what a run is.

    The strategy spends everything on AAA. Prices are flat at R$ 10, so
    the fill matches the price the decision saw and slippage is nil —
    which is the control: any drift here would mean the measurement had
    picked up something other than the decide-to-fill gap.
    """
    closes = {AAA: {date(2026, 1, day): Decimal(10) for day in range(1, 32)}}

    def strategy(state):
        return [Order(asset_id=AAA, ticker="AAA", side=Side.BUY, amount=state.cash)]

    run = simulate(
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        schedule=ContributionSchedule(amount=Decimal(1000), day_of_month=5),
        strategy=strategy,
        closes=closes,
        costs=FREE,
    )

    stats = trade_statistics(run)

    assert stats.trades == 1
    assert stats.buys == 1
    assert stats.contributed == Decimal(1000)
    assert stats.fees == ZERO
    assert stats.slippage == ZERO
    assert stats.closed_trades == 0


def test_the_fees_reported_are_the_ones_the_run_charged():
    """R$ 1.000 at R$ 10 is 100 shares; B3's 0,03% on R$ 1.000 is R$ 0,30."""
    closes = {AAA: {date(2026, 1, day): Decimal(10) for day in range(1, 32)}}

    def strategy(state):
        return [Order(asset_id=AAA, ticker="AAA", side=Side.BUY, amount=state.cash)]

    run = simulate(
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        schedule=ContributionSchedule(amount=Decimal(1000), day_of_month=5),
        strategy=strategy,
        closes=closes,
    )

    # 100 shares would cost 1000 + 0,30 > 1000, so 99 fill at R$ 990.
    assert trade_statistics(run).fees == Decimal("0.30")
