"""Tests for deriving a total-return series from raw closes.

The numbers are real. Every price step below was read off B3's own
archives, and every factor off B3's corporate-events service, so a test
that passes here is a test that reproduces what the market printed:

- BBAS3's 1:2 split on 2024-04-16 (56.46 -> 27.91),
- MGLU3's 1:10 regroup on 2024-05-27 (1.32 -> 13.15), the +896% session
  that ADR-023 exists to keep out of a return series,
- VIVT3 on 2025-04-15, a `DESDOBRAMENTO` of 7,900 and a `GRUPAMENTO` of
  0.025 going ex together and composing to exactly 2.0,
- ITUB4 on 2025-03-18, a real `EB` step of -8.60% that B3's events
  service does not report at all — the case that proves completeness has
  to be judged against the archive's counter and not against the service.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.data.models.assets import AssetPrice
from app.data.models.assets import CorporateAction as StoredAction
from app.domain.market_data.adjustment import adjusted_closes
from app.integrations.market_data.schemas import CorporateEvent, CorporateEventKind


def bar(day: date, close: str) -> AssetPrice:
    value = Decimal(close)
    return AssetPrice(
        asset_id=1,
        date=day,
        open=value,
        high=value,
        low=value,
        close=value,
        adjusted_close=None,
        volume=1000.0,
        source="b3_cotahist",
    )


def share_action(day: date, ratio: str, label: str = "DESDOBRAMENTO") -> StoredAction:
    return StoredAction(
        asset_id=1,
        ex_date=day,
        last_date_prior=day,
        kind="SPLIT",
        cash_amount=None,
        share_ratio=Decimal(ratio),
        label=label,
        source="b3_corporate_events",
    )


def cash_action(day: date, amount: str, label: str = "DIVIDENDO") -> StoredAction:
    return StoredAction(
        asset_id=1,
        ex_date=day,
        last_date_prior=day,
        kind="CASH_DIVIDEND",
        cash_amount=Decimal(amount),
        share_ratio=None,
        label=label,
        source="b3_corporate_events",
    )


def event(day: date, kind: CorporateEventKind) -> CorporateEvent:
    return CorporateEvent(
        date=day, kind=kind, specification="ON  ED  NM", distribution_number=1
    )


# -- the arithmetic ----------------------------------------------------


def test_a_split_restates_the_prices_before_it():
    """BBAS3's 1:2 on 2024-04-16, with the real closes around it."""
    bars = [
        bar(date(2024, 4, 12), "55.90"),
        bar(date(2024, 4, 15), "56.46"),
        bar(date(2024, 4, 16), "27.91"),
        bar(date(2024, 4, 17), "28.10"),
    ]
    actions = [share_action(date(2024, 4, 16), "2")]
    events = [event(date(2024, 4, 16), CorporateEventKind.BONUS_OR_SPLIT)]

    result = adjusted_closes(bars, actions, events)

    # After the split nothing moves; before it, everything halves.
    assert result.adjusted[date(2024, 4, 17)] == Decimal("28.100000")
    assert result.adjusted[date(2024, 4, 16)] == Decimal("27.910000")
    assert result.adjusted[date(2024, 4, 15)] == Decimal("28.230000")
    assert result.adjusted[date(2024, 4, 12)] == Decimal("27.950000")


def test_the_reverse_split_that_reads_as_896_percent_is_undone():
    """MGLU3 on 2024-05-27 — the session ADR-023 was written about.

    Raw, this is R$ 1.32 becoming R$ 13.15 and volatility reading a
    +896% day. Adjusted, the two sessions are within a rounding of each
    other and the day is the non-event it really was.
    """
    bars = [bar(date(2024, 5, 24), "1.32"), bar(date(2024, 5, 27), "13.15")]
    actions = [share_action(date(2024, 5, 27), "0.10", "GRUPAMENTO")]
    events = [event(date(2024, 5, 27), CorporateEventKind.REVERSE_SPLIT)]

    result = adjusted_closes(bars, actions, events)

    before = result.adjusted[date(2024, 5, 24)]
    after = result.adjusted[date(2024, 5, 27)]
    assert before == Decimal("13.200000")
    # A 0.4% step instead of 896%.
    assert abs(after / before - 1) < Decimal("0.005")


def test_a_dividend_restates_the_past_by_the_cash_that_left():
    """A R$1 payout on a R$50 share scales earlier closes by 0.98."""
    bars = [
        bar(date(2025, 3, 10), "50.00"),
        bar(date(2025, 3, 11), "49.00"),
    ]
    actions = [cash_action(date(2025, 3, 11), "1.00")]
    events = [event(date(2025, 3, 11), CorporateEventKind.DIVIDEND)]

    result = adjusted_closes(bars, actions, events)

    assert result.adjusted[date(2025, 3, 11)] == Decimal("49.000000")
    assert result.adjusted[date(2025, 3, 10)] == Decimal("49.000000")


def test_two_actions_on_one_session_compose():
    """VIVT3 on 2025-04-15: a 7,900% split and a 0.025 regroup together.

    They multiply to exactly 2.0, against a measured step of 51.00 ->
    25.46. Applying either alone would be wrong by a factor of forty.
    """
    bars = [bar(date(2025, 4, 14), "51.00"), bar(date(2025, 4, 15), "25.46")]
    actions = [
        share_action(date(2025, 4, 15), "80", "DESDOBRAMENTO"),
        share_action(date(2025, 4, 15), "0.025", "GRUPAMENTO"),
    ]
    events = [event(date(2025, 4, 15), CorporateEventKind.BONUS_OR_SPLIT)]

    result = adjusted_closes(bars, actions, events)

    assert result.adjusted[date(2025, 4, 14)] == Decimal("25.500000")


def test_the_most_recent_close_is_never_restated():
    bars = [bar(date(2025, 1, 2), "10.00"), bar(date(2025, 1, 3), "5.00")]
    actions = [share_action(date(2025, 1, 3), "2")]
    events = [event(date(2025, 1, 3), CorporateEventKind.BONUS_OR_SPLIT)]

    result = adjusted_closes(bars, actions, events)

    assert result.adjusted[date(2025, 1, 3)] == Decimal("5.000000")
    assert result.last_adjustable == date(2025, 1, 3)


# -- completeness ------------------------------------------------------


def test_a_counted_session_with_no_sized_action_bounds_the_series():
    """ITUB4's `EB` of 2025-03-18, which the events service omits.

    The archive counted it and the price stepped -8.60%. Adjusting
    through it would restate every earlier close by a factor nobody
    published, so the series simply starts after it.
    """
    bars = [
        bar(date(2025, 3, 17), "35.34"),
        bar(date(2025, 3, 18), "32.30"),
        bar(date(2025, 3, 19), "32.38"),
    ]
    events = [event(date(2025, 3, 18), CorporateEventKind.BONUS_OR_SPLIT)]

    result = adjusted_closes(bars, [], events)

    assert result.unaccounted == [date(2025, 3, 18)]
    assert result.first_adjustable == date(2025, 3, 19)
    assert date(2025, 3, 17) not in result.adjusted
    assert date(2025, 3, 18) not in result.adjusted


def test_only_the_most_recent_gap_bounds_the_series():
    bars = [bar(date(2025, 1, day), "10.00") for day in (2, 3, 6, 7, 8)]
    events = [
        event(date(2025, 1, 3), CorporateEventKind.UNCLASSIFIED),
        event(date(2025, 1, 7), CorporateEventKind.UNCLASSIFIED),
    ]

    result = adjusted_closes(bars, [], events)

    assert result.unaccounted == [date(2025, 1, 3), date(2025, 1, 7)]
    assert result.first_adjustable == date(2025, 1, 8)


def test_a_nominal_update_needs_no_magnitude_and_does_not_bound_anything():
    """PETR4's five `ATZ` sessions, which carry no entitlement.

    Reading them as missing magnitudes is what would cut PETR4's
    adjustable history from 1,495 sessions to 28. See
    `CorporateEventKind.NOMINAL_UPDATE` and ADR-026.
    """
    bars = [
        bar(date(2025, 8, 8), "30.53"),
        bar(date(2025, 8, 11), "30.72"),
        bar(date(2025, 8, 12), "30.80"),
    ]
    events = [event(date(2025, 8, 11), CorporateEventKind.NOMINAL_UPDATE)]

    result = adjusted_closes(bars, [], events)

    assert result.unaccounted == []
    assert result.first_adjustable == date(2025, 8, 8)
    # Nothing went ex, so nothing is restated.
    assert result.adjusted[date(2025, 8, 8)] == Decimal("30.530000")


def test_an_event_outside_the_stored_prices_cannot_bound_them():
    bars = [bar(date(2025, 6, 2), "10.00"), bar(date(2025, 6, 3), "10.10")]
    events = [event(date(2024, 1, 4), CorporateEventKind.DIVIDEND)]

    result = adjusted_closes(bars, [], events)

    assert result.unaccounted == []
    assert len(result.adjusted) == 2


def test_a_series_with_no_events_at_all_is_adjusted_end_to_end():
    bars = [bar(date(2025, 6, day), "10.00") for day in (2, 3, 4)]

    result = adjusted_closes(bars, [], [])

    assert len(result.adjusted) == 3
    assert result.first_adjustable == date(2025, 6, 2)


# -- what cannot be expressed -----------------------------------------


def test_a_payout_at_least_as_large_as_the_price_is_refused():
    """No factor expresses it, and a zero or negative one would put a
    nonsense price into every earlier session."""
    bars = [
        bar(date(2025, 5, 5), "1.00"),
        bar(date(2025, 5, 6), "0.90"),
        bar(date(2025, 5, 7), "0.95"),
    ]
    actions = [cash_action(date(2025, 5, 6), "1.50")]
    events = [event(date(2025, 5, 6), CorporateEventKind.DIVIDEND)]

    result = adjusted_closes(bars, actions, events)

    assert result.unusable == [date(2025, 5, 6)]
    assert result.first_adjustable == date(2025, 5, 6)
    assert date(2025, 5, 5) not in result.adjusted


def test_an_action_on_the_very_first_stored_session_restates_nothing():
    bars = [bar(date(2025, 5, 5), "10.00"), bar(date(2025, 5, 6), "10.10")]
    actions = [cash_action(date(2025, 5, 5), "0.50")]
    events = [event(date(2025, 5, 5), CorporateEventKind.DIVIDEND)]

    result = adjusted_closes(bars, actions, events)

    assert result.unusable == []
    assert result.adjusted[date(2025, 5, 5)] == Decimal("10.000000")


def test_no_prices_yields_nothing_rather_than_failing():
    result = adjusted_closes([], [], [])

    assert result.adjusted == {}
    assert result.first_adjustable is None


@pytest.mark.parametrize("ratio", ["0", "-1"])
def test_a_non_positive_ratio_is_refused(ratio):
    bars = [bar(date(2025, 5, 5), "10.00"), bar(date(2025, 5, 6), "10.10")]
    actions = [
        StoredAction(
            asset_id=1,
            ex_date=date(2025, 5, 6),
            last_date_prior=date(2025, 5, 5),
            kind="SPLIT",
            cash_amount=None,
            share_ratio=Decimal(ratio),
            label="DESDOBRAMENTO",
            source="b3_corporate_events",
        )
    ]

    result = adjusted_closes(bars, actions, [])

    assert result.unusable == [date(2025, 5, 6)]
    assert date(2025, 5, 5) not in result.adjusted
