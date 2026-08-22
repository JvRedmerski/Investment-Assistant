"""The intraday bar contract (W15-001).

Every claim these tests lock in was measured against a live Brapi
response on 2026-08-22 before it was written down — the procedure the
IMPLEMENTATION_GUIDE requires of any new integration, and the one whose
absence cost W06-003.
"""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.integrations.market_data.schemas import (
    HistoryWindow,
    IntradayBar,
    Timeframe,
)


def _bar(**overrides) -> IntradayBar:
    base = {
        "timestamp": datetime(2026, 8, 18, 13, 15, tzinfo=UTC),
        "timeframe": Timeframe.FIFTEEN_MINUTES,
        "open": Decimal("42.92"),
        "high": Decimal("43.10"),
        "low": Decimal("42.85"),
        "close": Decimal("43.07"),
        "volume": Decimal(1186700),
    }
    base.update(overrides)
    return IntradayBar(**base)


class TestTimeframe:
    def test_the_three_sizes_rule_47_names(self):
        assert [tf.value for tf in Timeframe] == ["1m", "5m", "15m"]

    @pytest.mark.parametrize(
        ("timeframe", "seconds"),
        [
            (Timeframe.ONE_MINUTE, 60),
            (Timeframe.FIVE_MINUTES, 300),
            (Timeframe.FIFTEEN_MINUTES, 900),
        ],
    )
    def test_seconds_is_the_cadence_a_gap_is_measured_against(self, timeframe, seconds):
        assert timeframe.seconds == seconds

    def test_it_is_a_string_enum_so_it_round_trips_through_storage(self):
        assert Timeframe("15m") is Timeframe.FIFTEEN_MINUTES
        assert str(Timeframe.FIFTEEN_MINUTES.value) == "15m"


class TestHistoryWindow:
    def test_the_four_buckets_the_vendor_serves(self):
        assert [w.value for w in HistoryWindow] == ["1d", "5d", "1mo", "3mo"]

    def test_it_round_trips_because_it_is_stored_on_the_row(self):
        assert HistoryWindow("3mo") is HistoryWindow.THREE_MONTHS


class TestIntradayBarTimestamp:
    def test_a_naive_timestamp_is_rejected(self):
        """Rule 18: a one-minute bar without a timezone is a bar without
        a time. Nothing may guess which one was meant."""
        with pytest.raises(ValidationError, match="must carry a timezone"):
            _bar(timestamp=datetime(2026, 8, 18, 13, 15))  # noqa: DTZ001

    def test_an_aware_timestamp_is_kept_as_given(self):
        stamp = datetime(2026, 8, 18, 13, 15, tzinfo=UTC)
        assert _bar(timestamp=stamp).timestamp == stamp

    def test_a_non_utc_offset_is_accepted_and_still_names_one_instant(self):
        """Awareness is the requirement, not UTC. Normalising to UTC is
        the ingestion's job, and these two are the same instant."""
        local = datetime(2026, 8, 18, 10, 15, tzinfo=timezone(timedelta(hours=-3)))
        assert _bar(timestamp=local).timestamp == datetime(
            2026, 8, 18, 13, 15, tzinfo=UTC
        )


class TestIntradayBarShape:
    def test_it_carries_no_adjusted_close(self):
        """Measured: `adjustedClose` was null on 1,389 of 1,389 live
        intraday bars across all three timeframes. A field that is
        always null is an absent field, and one this project must not
        invite anyone to fill in (ADR-023)."""
        assert "adjusted_close" not in IntradayBar.model_fields

    def test_prices_are_decimal_not_float(self):
        bar = _bar(open=42.92)
        assert isinstance(bar.open, Decimal)

    def test_negative_volume_is_rejected(self):
        with pytest.raises(ValidationError):
            _bar(volume=Decimal(-1))

    def test_zero_volume_is_accepted(self):
        """Measured: the 17:00 closing print comes back with volume 0.
        It is a real bar the source published, not a malformed one."""
        assert _bar(volume=Decimal(0)).volume == Decimal(0)

    def test_an_unknown_timeframe_is_rejected(self):
        with pytest.raises(ValidationError):
            _bar(timeframe="30m")
