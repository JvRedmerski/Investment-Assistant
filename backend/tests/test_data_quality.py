"""Unit tests for validate_daily_bars (AGENTS.md rule 68: known input ->
known output)."""

from datetime import date
from decimal import Decimal

from app.integrations.market_data.data_quality import validate_daily_bars
from app.integrations.market_data.schemas import DailyBar


def _bar(
    day: int,
    open_="38.0",
    high="39.0",
    low="37.5",
    close="38.5",
    adjusted_close=None,
    volume="1000000",
) -> DailyBar:
    return DailyBar(
        date=date(2026, 1, day),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        adjusted_close=Decimal(adjusted_close if adjusted_close is not None else close),
        volume=Decimal(volume),
    )


def test_valid_bars_pass_with_no_errors_or_warnings():
    bars = [_bar(2), _bar(3)]

    report = validate_daily_bars(bars)

    assert report.is_valid
    assert report.valid_bars == bars
    assert report.errors == []
    assert report.warnings == []
    assert report.rejected_count == 0


def test_rejects_non_positive_price():
    bad = _bar(2, low="0")

    report = validate_daily_bars([bad])

    assert not report.is_valid
    assert report.valid_bars == []
    assert report.rejected_count == 1
    assert report.errors[0].code == "NON_POSITIVE_PRICE"


def test_rejects_negative_volume():
    # DailyBar's own schema already forbids negative volume (Field(ge=0)),
    # so a normal constructor call can never produce one; bypass it with
    # model_construct to exercise the validator's defense-in-depth check
    # directly (AGENTS.md rule 19 — never assume a caller already validated).
    bad = DailyBar.model_construct(
        date=date(2026, 1, 2),
        open=Decimal("38.0"),
        high=Decimal("39.0"),
        low=Decimal("37.5"),
        close=Decimal("38.5"),
        adjusted_close=Decimal("38.5"),
        volume=Decimal(-1),
    )

    report = validate_daily_bars([bad])

    assert report.errors[0].code == "INVALID_VOLUME"


def test_rejects_invalid_ohlc_when_low_above_open():
    bad = _bar(2, open_="10", high="20", low="15", close="18")

    report = validate_daily_bars([bad])

    assert report.errors[0].code == "INVALID_OHLC"


def test_rejects_invalid_ohlc_when_high_below_close():
    bad = _bar(2, open_="10", high="12", low="9", close="20")

    report = validate_daily_bars([bad])

    assert report.errors[0].code == "INVALID_OHLC"


def test_rejects_both_bars_sharing_a_duplicate_date():
    first = _bar(2, close="38.0")
    second = _bar(2, close="39.0")

    report = validate_daily_bars([first, second])

    assert report.rejected_count == 2
    assert all(issue.code == "DUPLICATE_DATE" for issue in report.errors)
    assert report.valid_bars == []


def test_out_of_order_input_produces_a_warning_but_bars_stay_valid():
    bars = [_bar(3), _bar(2)]

    report = validate_daily_bars(bars)

    assert report.is_valid
    assert len(report.valid_bars) == 2
    assert any(w.code == "OUT_OF_ORDER" for w in report.warnings)


def test_absurd_move_produces_a_warning_but_the_bar_stays_valid():
    bars = [
        _bar(2, close="10.00", low="9", high="11", open_="10"),
        _bar(3, close="20.00", low="19", high="21", open_="20"),
    ]

    report = validate_daily_bars(bars)

    assert report.is_valid
    assert len(report.valid_bars) == 2
    assert any(w.code == "ABSURD_MOVE" for w in report.warnings)


def test_small_move_does_not_produce_a_warning():
    bars = [
        _bar(2, close="10.00", low="9", high="11", open_="10"),
        _bar(3, close="10.50"),
    ]

    report = validate_daily_bars(bars)

    assert report.warnings == []


def test_empty_input_is_valid_and_produces_nothing():
    report = validate_daily_bars([])

    assert report.is_valid
    assert report.valid_bars == []
    assert report.warnings == []
