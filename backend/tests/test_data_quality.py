"""Unit tests for validate_daily_bars (AGENTS.md rule 68: known input ->
known output)."""

from datetime import date
from decimal import Decimal

from app.integrations.market_data.data_quality import validate_daily_bars
from app.integrations.market_data.schemas import DailyBar

#: Sentinel for `_bar(adjusted_close=...)`: distinguishes "caller did not
#: specify, mirror the close" from "the source reported no adjustment".
_UNSET = object()


def _bar(
    day: int,
    open_="38.0",
    high="39.0",
    low="37.5",
    close="38.5",
    adjusted_close=_UNSET,
    volume="1000000",
) -> DailyBar:
    if adjusted_close is _UNSET:
        adjusted_close = close
    return DailyBar(
        date=date(2026, 1, day),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        adjusted_close=(
            Decimal(adjusted_close) if adjusted_close is not None else None
        ),
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


def test_bar_without_an_adjusted_close_is_rejected_not_backfilled_from_close():
    """A bar the source did not adjust must not reach storage.

    Returns (Wave 07) are computed from `adjusted_close`, the column is
    `NOT NULL`, and `sync_daily_history` never rewrites a stored date. So
    accepting this bar would mean freezing a fabricated adjustment
    permanently. Rejecting leaves the date absent, and a later sync
    inserts it once the source publishes the real figure.

    Verified against live data on 2026-08-18: Brapi returned
    `adjustedClose: null` for the most recently closed session on
    HGLG11, BOVA11 and ITUB4 alike.
    """
    bars = [_bar(2), _bar(3, adjusted_close=None)]

    report = validate_daily_bars(bars)

    assert not report.is_valid
    assert report.rejected_count == 1
    assert [bar.date for bar in report.valid_bars] == [date(2026, 1, 2)]
    (issue,) = report.errors
    assert issue.code == "MISSING_ADJUSTED_CLOSE"
    assert issue.bar_date == date(2026, 1, 3)


def test_an_adjusted_close_differing_from_close_is_kept_as_reported():
    # The normal ex-dividend case: the adjustment is real and must survive
    # untouched, which is exactly what the fabricated fallback destroyed.
    bars = [_bar(2, close="38.5", adjusted_close="37.9")]

    report = validate_daily_bars(bars)

    assert report.is_valid
    assert report.valid_bars[0].adjusted_close == Decimal("37.9")
    assert report.valid_bars[0].close == Decimal("38.5")
