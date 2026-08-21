"""Tests for the pure backtest engine (W13-002).

Known inputs, known outputs — the standard rule 68 asks for. The cases
that matter most are the ones about *time*: that a decision made on a
session fills on the next one, and that money and shares only ever move
for a reason the result can name.
"""

from datetime import date
from decimal import Decimal

from app.data.models.portfolio import TransactionTypeEnum
from app.domain.backtesting.simulation import (
    BELOW_ONE_SHARE,
    NO_PRICE,
    CashAction,
    ContributionSchedule,
    CostModel,
    Order,
    Side,
    SimulationState,
    contribution_sessions,
    simulate,
    whole_shares,
)
from app.domain.portfolio.service import ShareAdjustment, compute_positions

AAA = 1
BBB = 2

FREE = CostModel(exchange_rate=Decimal(0))


def _closes(asset_id: int, *pairs: tuple[int, str]) -> dict[int, dict[date, Decimal]]:
    return {asset_id: {date(2026, 1, day): Decimal(value) for day, value in pairs}}


def _buy_everything(ticker: str = "AAA", asset_id: int = AAA):
    """A strategy that spends all its cash on one asset."""

    def strategy(state: SimulationState) -> list[Order]:
        return [
            Order(asset_id=asset_id, ticker=ticker, side=Side.BUY, amount=state.cash)
        ]

    return strategy


def _run(strategy, closes, **kwargs):
    return simulate(
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        schedule=kwargs.pop(
            "schedule", ContributionSchedule(amount=Decimal(1000), day_of_month=1)
        ),
        strategy=strategy,
        closes=closes,
        costs=kwargs.pop("costs", FREE),
        **kwargs,
    )


# -- when a decision becomes a trade ----------------------------------


def test_an_order_fills_on_the_session_after_the_decision():
    """Rule 58: a close can only be read once it has printed."""
    closes = _closes(AAA, (2, "10"), (5, "20"))
    result = _run(_buy_everything(), closes)

    trades = [tx for tx in result.transactions if tx.type is TransactionTypeEnum.BUY]
    assert len(trades) == 1
    # Decided on the 2nd at R$ 10; filled on the 5th at R$ 20, which is
    # worse — and that is the point. Filling at the decision price would
    # have bought at a price nobody could have traded at.
    assert trades[0].transaction_date.date() == date(2026, 1, 5)
    assert trades[0].price == Decimal(20)
    assert trades[0].quantity == Decimal(50)


def test_the_decision_only_sees_the_session_it_was_made_on():
    seen: list[SimulationState] = []

    def spy(state: SimulationState) -> list[Order]:
        seen.append(state)
        return []

    _run(spy, _closes(AAA, (2, "10"), (5, "20")))

    (state,) = seen
    assert state.day == date(2026, 1, 2)
    assert state.closes == {AAA: Decimal(10)}


def test_a_fill_is_recorded_against_the_decision_that_caused_it():
    result = _run(_buy_everything(), _closes(AAA, (2, "10"), (5, "20")))

    (decision,) = result.decisions
    assert decision.day == date(2026, 1, 2)
    assert decision.cash_before == Decimal(1000)
    assert [fill.quantity for fill in decision.fills] == [Decimal(50)]


# -- money that does not get spent ------------------------------------


def test_only_whole_shares_are_bought_and_the_rest_stays_as_cash():
    """Nobody buys 3.7 shares; the remainder reaches the next month."""
    closes = _closes(AAA, (2, "10"), (5, "30"))
    result = _run(_buy_everything(), closes)

    trades = [tx for tx in result.transactions if tx.type is TransactionTypeEnum.BUY]
    assert trades[0].quantity == Decimal(33)
    assert result.cash_on(date(2026, 1, 5)) == Decimal(10)


def test_fees_leave_the_cash_and_are_reported():
    closes = _closes(AAA, (2, "10"), (5, "25"))
    result = _run(_buy_everything(), closes, costs=CostModel())

    # 39 shares at 25 is 975, whose fee is 975 * 0.0003 = 0,2925 -> 0,30.
    # The 40th share would cost 1.000,30 against 1.000 of cash.
    trades = [tx for tx in result.transactions if tx.type is TransactionTypeEnum.BUY]
    assert trades[0].quantity == Decimal(39)
    assert trades[0].fees == Decimal("0.30")
    assert result.fees_paid == Decimal("0.30")
    assert result.cash_on(date(2026, 1, 5)) == Decimal("24.70")


def test_an_amount_below_one_share_is_reported_and_not_traded():
    closes = _closes(AAA, (2, "10"), (5, "20"))

    def tiny(state: SimulationState) -> list[Order]:
        return [Order(asset_id=AAA, ticker="AAA", side=Side.BUY, amount=Decimal(5))]

    result = _run(tiny, closes)

    assert not [tx for tx in result.transactions if tx.type is TransactionTypeEnum.BUY]
    (decision,) = result.decisions
    assert [fill.reason for fill in decision.fills] == [BELOW_ONE_SHARE]


def test_an_order_for_an_asset_with_no_price_that_session_is_named():
    """Never a fabricated price to fill against (rule 44)."""
    closes = {**_closes(AAA, (2, "10"), (5, "20")), BBB: {date(2026, 1, 2): Decimal(7)}}

    def buy_bbb(state: SimulationState) -> list[Order]:
        return [Order(asset_id=BBB, ticker="BBB", side=Side.BUY, amount=Decimal(100))]

    result = _run(buy_bbb, closes)

    (decision,) = result.decisions
    assert [fill.reason for fill in decision.fills] == [NO_PRICE]


# -- dividends --------------------------------------------------------


def test_a_payout_credits_cash_in_proportion_to_the_holding():
    closes = _closes(AAA, (2, "10"), (5, "20"), (8, "20"))
    result = _run(
        _buy_everything(),
        closes,
        cash_actions=[
            CashAction(
                asset_id=AAA,
                ex_date=date(2026, 1, 8),
                amount_per_share=Decimal("0.50"),
            )
        ],
    )

    # 50 shares by then, at R$ 0,50 each.
    assert result.dividends_received == Decimal(25)
    assert result.cash_on(date(2026, 1, 8)) == Decimal(25)

    payouts = [
        tx for tx in result.transactions if tx.type is TransactionTypeEnum.DIVIDEND
    ]
    assert payouts[0].quantity == Decimal(50)
    assert payouts[0].price == Decimal("0.50")


def test_a_payout_before_anything_is_held_credits_nothing():
    closes = _closes(AAA, (2, "10"), (5, "20"))
    result = _run(
        _buy_everything(),
        closes,
        cash_actions=[
            CashAction(
                asset_id=AAA, ex_date=date(2026, 1, 2), amount_per_share=Decimal(1)
            )
        ],
    )

    assert result.dividends_received == Decimal(0)


def test_a_split_is_visible_to_the_engine_through_the_shared_replay():
    """The engine derives custody the same way the rest of the project does."""
    closes = _closes(AAA, (2, "10"), (5, "20"), (8, "10"))
    split = ShareAdjustment(
        asset_id=AAA, ex_date=date(2026, 1, 8), ratio=Decimal(2), label="DESDOBRAMENTO"
    )
    result = _run(
        _buy_everything(),
        closes,
        share_actions=[split],
        cash_actions=[
            CashAction(
                asset_id=AAA,
                ex_date=date(2026, 1, 8),
                amount_per_share=Decimal("0.50"),
            )
        ],
    )

    # 50 shares bought on the 5th; the split doubles them before the
    # payout on the 8th is measured.
    assert result.dividends_received == Decimal(50)
    positions = compute_positions(list(result.transactions), result.adjustments)
    assert positions[AAA].quantity == Decimal(100)


# -- the ledger it produces -------------------------------------------


def test_the_contribution_is_recorded_as_a_deposit():
    result = _run(_buy_everything(), _closes(AAA, (2, "10"), (5, "20")))

    deposits = [
        tx for tx in result.transactions if tx.type is TransactionTypeEnum.DEPOSIT
    ]
    assert len(deposits) == 1
    assert deposits[0].quantity == Decimal(1000)
    assert deposits[0].price == Decimal(1)
    assert deposits[0].asset_id is None
    assert result.contributed == Decimal(1000)


def test_nothing_happens_without_a_single_priced_session():
    result = _run(_buy_everything(), {})
    assert result.transactions == ()
    assert result.contributed == Decimal(0)


def test_the_same_inputs_produce_the_same_run():
    """Rule 113: the engine is deterministic even though the text is not."""
    closes = _closes(AAA, (2, "10"), (5, "20"), (8, "21"))
    first = _run(_buy_everything(), closes)
    second = _run(_buy_everything(), closes)

    assert [(tx.type, tx.quantity, tx.price) for tx in first.transactions] == [
        (tx.type, tx.quantity, tx.price) for tx in second.transactions
    ]
    assert first.cash_by_date == second.cash_by_date


# -- the schedule -----------------------------------------------------


def test_a_contribution_lands_on_the_first_session_on_or_after_its_day():
    calendar = [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 2, 2),
        date(2026, 2, 3),
    ]
    schedule = ContributionSchedule(amount=Decimal(1000), day_of_month=5)

    assert contribution_sessions(calendar, schedule) == [
        date(2026, 1, 5),
        date(2026, 2, 3),
    ]


def test_a_month_whose_target_never_arrives_still_contributes():
    """Money that arrived is money that arrived, not a skipped month."""
    calendar = [date(2026, 1, 2), date(2026, 1, 5)]
    schedule = ContributionSchedule(amount=Decimal(1000), day_of_month=28)

    assert contribution_sessions(calendar, schedule) == [date(2026, 1, 5)]


def test_whole_shares_never_divides_by_a_price_of_zero():
    assert whole_shares(Decimal(100), Decimal(0)) == Decimal(0)
    assert whole_shares(Decimal(100), Decimal("33.33")) == Decimal(3)
