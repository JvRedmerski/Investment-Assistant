"""Tests for valuing positions at market.

Pure function, hand-computed expectations (AGENTS.md rule 68). Every
amount is `quantity × close` worked out by hand, and every absence is
checked for being absent rather than zero.
"""

from datetime import date
from decimal import Decimal

from app.domain.portfolio.service import AssetPosition
from app.domain.portfolio.valuation import (
    ClosingPrice,
    value_positions,
)


def _position(asset_id: int, quantity: str, invested: str) -> AssetPosition:
    return AssetPosition(
        asset_id=asset_id,
        quantity=Decimal(quantity),
        average_price=(
            Decimal(invested) / Decimal(quantity)
            if Decimal(quantity) > 0
            else Decimal(0)
        ),
        invested_amount=Decimal(invested),
    )


def _quote(close: str, day: str = "2026-08-20") -> ClosingPrice:
    return ClosingPrice(date=date.fromisoformat(day), close=Decimal(close))


def _by_id(valuation):
    return {item.asset_id: item for item in valuation.positions}


# -- the arithmetic ---------------------------------------------------


def test_market_value_is_quantity_times_close():
    """100 shares bought at R$ 28 now printing R$ 30,82."""
    valuation = value_positions({1: _position(1, "100", "2800")}, {1: _quote("30.82")})

    row = _by_id(valuation)[1]
    assert row.market_value == Decimal("3082.00")
    assert row.unrealised_pnl == Decimal("282.00")
    assert row.last_price == Decimal("30.82")
    assert row.price_date == date(2026, 8, 20)


def test_a_position_under_water_reports_a_negative_unrealised_result():
    valuation = value_positions({1: _position(1, "100", "3500")}, {1: _quote("30.82")})

    assert _by_id(valuation)[1].unrealised_pnl == Decimal("-418.00")


def test_the_totals_are_the_sum_of_the_valued_rows():
    valuation = value_positions(
        {
            1: _position(1, "100", "2800"),
            2: _position(2, "50", "1000"),
        },
        {1: _quote("30.82"), 2: _quote("24.00")},
    )

    assert valuation.valued_market_value == Decimal("4282.00")
    assert valuation.valued_invested == Decimal(3800)
    assert valuation.unrealised_pnl == Decimal("482.00")
    assert valuation.is_complete


# -- absence ----------------------------------------------------------


def test_a_position_with_no_price_is_absent_not_zero():
    """ADR-014: the number that could not be computed says so."""
    valuation = value_positions({1: _position(1, "100", "2800")}, {})

    row = _by_id(valuation)[1]
    assert row.market_value is None
    assert row.unrealised_pnl is None
    assert row.last_price is None
    assert row.price_date is None
    assert not row.is_valued


def test_one_unpriced_asset_does_not_take_the_whole_total_with_it():
    """The choice this module makes, against two other precedents.

    `performance_index` blanks the whole day and the scoring engine
    sidesteps the question with cost basis. A positions table reads one
    row at a time, so only the row goes absent.
    """
    valuation = value_positions(
        {
            1: _position(1, "100", "2800"),
            2: _position(2, "50", "1000"),
        },
        {1: _quote("30.82")},
    )

    assert valuation.valued_market_value == Decimal("3082.00")
    assert valuation.unvalued_positions == 1
    assert valuation.unvalued_invested == Decimal(1000)
    assert not valuation.is_complete


def test_the_valued_total_is_compared_against_the_valued_cost_only():
    """Otherwise the unpriced position would be reported as a loss.

    R$ 2.800 priced at R$ 3.082 and R$ 1.000 unpriced. Against the whole
    R$ 3.800 of cost the result would read as a loss of R$ 718; against
    the R$ 2.800 it actually covers, it is a gain of R$ 282.
    """
    valuation = value_positions(
        {
            1: _position(1, "100", "2800"),
            2: _position(2, "50", "1000"),
        },
        {1: _quote("30.82")},
    )

    assert valuation.valued_invested == Decimal(2800)
    assert valuation.unrealised_pnl == Decimal("282.00")


def test_a_closed_position_is_worth_zero_rather_than_unknown():
    """Nothing held is a measurement, not a gap."""
    valuation = value_positions({1: _position(1, "0", "0")}, {})

    row = _by_id(valuation)[1]
    assert row.market_value == Decimal(0)
    assert row.unrealised_pnl == Decimal(0)
    assert valuation.unvalued_positions == 0
    assert valuation.is_complete


def test_an_empty_portfolio_is_worth_zero():
    valuation = value_positions({}, {})

    assert valuation.positions == ()
    assert valuation.valued_market_value == Decimal(0)
    assert valuation.oldest_price_date is None


# -- staleness (rules 103/104) ----------------------------------------


def test_the_price_window_is_reported():
    valuation = value_positions(
        {
            1: _position(1, "100", "2800"),
            2: _position(2, "50", "1000"),
        },
        {
            1: _quote("30.82", "2026-08-20"),
            2: _quote("24.00", "2026-05-14"),
        },
    )

    assert valuation.oldest_price_date == date(2026, 5, 14)
    assert valuation.newest_price_date == date(2026, 8, 20)


def test_a_closed_position_does_not_widen_the_price_window():
    """It contributes nothing to the total, so its date describes nothing.

    Letting a sold-out holding's stale quote drag `oldest_price_date`
    back would report the totals as older than the money in them.
    """
    valuation = value_positions(
        {
            1: _position(1, "100", "2800"),
            2: _position(2, "0", "0"),
        },
        {
            1: _quote("30.82", "2026-08-20"),
            2: _quote("9.00", "2024-01-05"),
        },
    )

    assert valuation.oldest_price_date == date(2026, 8, 20)
    # The price is still shown on the row: it is real information.
    assert _by_id(valuation)[2].last_price == Decimal("9.00")


def test_the_order_does_not_depend_on_the_dictionary():
    """Rule 113: same inputs, same order, every run."""
    positions = {
        3: _position(3, "10", "100"),
        1: _position(1, "10", "100"),
        2: _position(2, "10", "100"),
    }

    valuation = value_positions(positions, {})

    assert [item.asset_id for item in valuation.positions] == [1, 2, 3]
