"""Tests for the wealth curve and for aligning two series to one chart.

Pure functions, hand-computed expectations (AGENTS.md rule 68). The
example is one asset with round numbers, so every level below can be
checked in your head — which is the only way an error in the *test*
would be caught.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.data.models.portfolio import Transaction, TransactionTypeEnum
from app.domain.benchmarks.comparison import align
from app.domain.portfolio.performance import value_series
from app.quant.returns import PricePoint

ASSET = 1
OTHER = 2


def _tx(
    day: int,
    kind: TransactionTypeEnum,
    quantity="0",
    price="0",
    fees="0",
    asset_id=ASSET,
) -> Transaction:
    return Transaction(
        id=day,
        portfolio_id=1,
        asset_id=asset_id,
        type=kind,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fees=Decimal(fees),
        transaction_date=datetime(2026, 1, day, tzinfo=UTC),
    )


def _closes(*pairs, asset_id=ASSET) -> dict[int, dict[date, Decimal]]:
    return {asset_id: {date(2026, 1, day): Decimal(price) for day, price in pairs}}


def _points(*pairs) -> list[PricePoint]:
    return [
        PricePoint(date=date(2026, 1, day), adjusted_close=Decimal(level))
        for day, level in pairs
    ]


def _levels(points) -> list[Decimal]:
    return [point.adjusted_close for point in points]


# -- the wealth curve --------------------------------------------------


def test_the_curve_is_holdings_at_the_raw_close():
    """100 shares at 10, price 10 -> 12: R$ 1.000 becomes R$ 1.200."""
    points = value_series(
        [_tx(1, TransactionTypeEnum.BUY, "100", "10")],
        _closes((1, "10"), (2, "12")),
    )

    assert [(p.date.day, p.value, p.invested) for p in points] == [
        (1, Decimal(1000), Decimal(1000)),
        (2, Decimal(1200), Decimal(1000)),
    ]


def test_a_contribution_raises_the_cost_line_as_well_as_the_value():
    """The whole reason both lines exist.

    R$ 1.000 in on day 1 and R$ 1.000 more on day 2, with the price
    flat. The value doubles and so does the cost — no performance at
    all, which the value line alone would look identical to.
    """
    points = value_series(
        [
            _tx(1, TransactionTypeEnum.BUY, "100", "10"),
            _tx(2, TransactionTypeEnum.BUY, "100", "10"),
        ],
        _closes((1, "10"), (2, "10")),
    )

    assert [(p.value, p.invested) for p in points] == [
        (Decimal(1000), Decimal(1000)),
        (Decimal(2000), Decimal(2000)),
    ]


def test_fees_are_part_of_what_was_put_in():
    """They leave the investor's pocket and never become value."""
    points = value_series(
        [_tx(1, TransactionTypeEnum.BUY, "100", "10", fees="15")],
        _closes((1, "10")),
    )

    assert points[0].value == Decimal(1000)
    assert points[0].invested == Decimal(1015)


def test_a_sale_lowers_the_cost_line():
    points = value_series(
        [
            _tx(1, TransactionTypeEnum.BUY, "100", "10"),
            _tx(2, TransactionTypeEnum.SELL, "40", "12"),
        ],
        _closes((1, "10"), (2, "12")),
    )

    # 60 shares left at 12, against 1000 put in less 480 taken out.
    assert points[-1].value == Decimal(720)
    assert points[-1].invested == Decimal(520)


def test_a_date_missing_a_price_for_one_holding_is_skipped():
    """A total missing one holding is a different portfolio, not a smaller one."""
    transactions = [
        _tx(1, TransactionTypeEnum.BUY, "100", "10"),
        _tx(1, TransactionTypeEnum.BUY, "50", "20", asset_id=OTHER),
    ]
    closes = _closes((1, "10"), (2, "12"))
    closes[OTHER] = {date(2026, 1, 1): Decimal(20)}

    points = value_series(transactions, closes)

    assert [p.date.day for p in points] == [1]
    assert points[0].value == Decimal(2000)


def test_nothing_after_as_of_is_read():
    points = value_series(
        [_tx(1, TransactionTypeEnum.BUY, "100", "10")],
        _closes((1, "10"), (2, "12"), (3, "15")),
        as_of=date(2026, 1, 2),
    )

    assert [p.date.day for p in points] == [1, 2]


def test_a_portfolio_with_no_transactions_has_no_curve():
    assert value_series([], _closes((1, "10"))) == []


# -- aligning two series -----------------------------------------------


def test_a_series_is_rebased_to_the_base():
    """Whatever it started at, it leaves at 100."""
    aligned = align(_points((1, "200"), (2, "220"), (3, "210")))

    assert _levels(aligned.subject) == [Decimal(100), Decimal(110), Decimal(105)]
    assert aligned.base_date == date(2026, 1, 1)
    assert aligned.end_date == date(2026, 1, 3)
    assert aligned.benchmark == ()


def test_both_series_leave_the_same_place():
    """An index at 130.000 and a compounded CDI at 1.07 both reach 100."""
    aligned = align(
        _points((1, "130000"), (2, "143000")),
        _points((1, "1.00"), (2, "1.07")),
    )

    assert _levels(aligned.subject) == [Decimal(100), Decimal(110)]
    assert _levels(aligned.benchmark) == [Decimal(100), Decimal(107)]


def test_the_window_is_the_intersection_not_the_union():
    """The benchmark gets no head start the reader cannot see.

    The benchmark rises 20% over two days before the portfolio has its
    first valuation. Drawn from its own start it would appear to be
    winning by that 20%; clipped to the shared window it leaves 100 on
    the same day the portfolio does.
    """
    aligned = align(
        _points((3, "100"), (4, "110")),
        _points((1, "100"), (2, "110"), (3, "120"), (4, "126")),
    )

    assert aligned.base_date == date(2026, 1, 3)
    assert _levels(aligned.subject) == [Decimal(100), Decimal(110)]
    assert _levels(aligned.benchmark) == [Decimal(100), Decimal(105)]


def test_the_window_also_closes_at_the_earlier_ending():
    aligned = align(
        _points((1, "100"), (2, "110")),
        _points((1, "100"), (2, "105"), (3, "130")),
    )

    assert aligned.end_date == date(2026, 1, 2)
    assert [p.date.day for p in aligned.benchmark] == [1, 2]


def test_a_date_only_one_series_has_is_not_invented_for_the_other():
    """Rule 44: a point drawn to make a line continuous is a fabricated price."""
    aligned = align(
        _points((1, "100"), (2, "110"), (3, "120")),
        _points((1, "100"), (3, "105")),
    )

    assert [p.date.day for p in aligned.subject] == [1, 2, 3]
    assert [p.date.day for p in aligned.benchmark] == [1, 3]


def test_two_series_that_never_overlap_produce_nothing():
    """A real answer: they cannot be drawn against each other."""
    aligned = align(_points((5, "100")), _points((1, "100"), (2, "110")))

    assert aligned.subject == ()
    assert aligned.benchmark == ()
    assert aligned.base_date is None


def test_an_empty_subject_produces_nothing():
    assert align([], _points((1, "100"))).subject == ()
