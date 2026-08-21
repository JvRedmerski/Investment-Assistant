"""Tests for `app.domain.ai.formatting`.

The contract these pin down is narrow and load-bearing: the string the
model is handed must be the string the screen shows. Every expected
value below was chosen to match `frontend/src/lib/format.ts`, which is
`Intl.NumberFormat('pt-BR')` — so a change here that "looks nicer" but
drifts from the frontend breaks the property the whole wave rests on.
"""

from datetime import date
from decimal import Decimal

from app.domain.ai import formatting


def test_money_matches_the_frontend_rendering():
    assert formatting.money(Decimal("1234.5")) == "R$ 1.234,50"
    assert formatting.money(Decimal(0)) == "R$ 0,00"
    assert formatting.money(Decimal("-42.125")) == "R$ -42,13"


def test_money_groups_every_three_digits():
    assert formatting.money(Decimal("1234567.891")) == "R$ 1.234.567,89"


def test_percent_converts_a_fraction_and_keeps_one_digit():
    assert formatting.percent(Decimal("0.12384")) == "12,4%"
    assert formatting.percent(Decimal("-0.634")) == "-63,4%"
    assert formatting.percent(Decimal(0)) == "0,0%"


def test_percent_rounds_half_away_from_zero_like_the_frontend():
    """ECMA-402 rounds half-expand; `ROUND_HALF_UP` is its Python twin.

    Pinned because a half-even default here would put `12,4%` on the
    screen and `12,3%` in the sentence underneath it.
    """
    assert formatting.percent(Decimal("0.1235")) == "12,4%"
    assert formatting.percent(Decimal("-0.1235")) == "-12,4%"


def test_points_is_signed_and_labelled():
    assert formatting.points(Decimal("0.0712")) == "+7,1 p.p."
    assert formatting.points(Decimal("-0.0712")) == "-7,1 p.p."


def test_points_leaves_zero_unsigned():
    """A `+` on zero would suggest an advantage that is not there."""
    assert formatting.points(Decimal(0)) == "0,0 p.p."


def test_decimal_value_carries_two_digits_for_scores_and_ratios():
    assert formatting.decimal_value(Decimal("0.8351")) == "0,84"
    assert formatting.decimal_value(Decimal("76.7231")) == "76,72"


def test_count_groups_but_never_adds_decimals():
    assert formatting.count(1495) == "1.495"
    assert formatting.count(0) == "0"


def test_short_date_is_day_first_and_zero_padded():
    assert formatting.short_date(date(2026, 8, 21)) == "21/08/2026"
    assert formatting.short_date(date(2020, 1, 2)) == "02/01/2020"


def test_absence_is_a_dash_in_every_formatter():
    """ADR-014: `None` is "not computable", and it never renders as zero."""
    assert formatting.money(None) == formatting.ABSENT
    assert formatting.percent(None) == formatting.ABSENT
    assert formatting.points(None) == formatting.ABSENT
    assert formatting.decimal_value(None) == formatting.ABSENT
    assert formatting.count(None) == formatting.ABSENT
    assert formatting.short_date(None) == formatting.ABSENT
    assert formatting.ABSENT == "—"
