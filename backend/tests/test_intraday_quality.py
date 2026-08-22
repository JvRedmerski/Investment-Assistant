"""Intraday data quality and gap detection (W15-003).

The regression cases at the bottom are real PETR4 bars captured on
2026-08-22, including the one session in the capture that is genuinely
short. They are here because that session is what decided the design:
its bars sit on a different minute-phase from every other session, so a
grid-alignment check would have thrown away sixteen real prices and
reported a malformed session instead of a short one.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import ClassVar

import pytest

from app.integrations.market_data.intraday_quality import (
    EXCHANGE_TIMEZONE,
    _typical_bar_count,
    session_date,
    validate_intraday_bars,
)
from app.integrations.market_data.schemas import IntradayBar, Timeframe

_15M = Timeframe.FIFTEEN_MINUTES


def _bar(
    moment: datetime,
    *,
    close: str = "42.00",
    timeframe: Timeframe = _15M,
    open_: str | None = None,
    high: str | None = None,
    low: str | None = None,
    volume: str = "1000",
) -> IntradayBar:
    price = Decimal(close)
    return IntradayBar(
        timestamp=moment,
        timeframe=timeframe,
        open=Decimal(open_) if open_ is not None else price,
        high=Decimal(high) if high is not None else price,
        low=Decimal(low) if low is not None else price,
        close=price,
        volume=Decimal(volume),
    )


def _local(day: date, hour: int, minute: int) -> datetime:
    return datetime(
        day.year, day.month, day.day, hour, minute, tzinfo=EXCHANGE_TIMEZONE
    )


def _session(day: date, count: int, *, start_minute: int = 15) -> list[IntradayBar]:
    """A clean run of `count` 15-minute bars starting at 10:`start_minute`."""
    first = _local(day, 10, start_minute)
    return [_bar(first + timedelta(minutes=15 * i)) for i in range(count)]


class TestSessionDate:
    def test_an_instant_is_grouped_by_its_local_date(self):
        """13:15 UTC is 10:15 in B3's session on the same calendar day."""
        assert session_date(datetime(2026, 8, 18, 13, 15, tzinfo=UTC)) == date(
            2026, 8, 18
        )

    def test_an_instant_after_utc_midnight_belongs_to_the_previous_session(self):
        """Not reachable for B3 today, and the point of converting rather
        than reading the UTC date: the rule must not depend on the
        offset happening to keep a session inside one UTC day."""
        assert session_date(datetime(2026, 8, 19, 1, 30, tzinfo=UTC)) == date(
            2026, 8, 18
        )


class TestBarLevelValidity:
    def test_a_clean_session_produces_no_issues(self):
        report = validate_intraday_bars(_session(date(2026, 8, 18), 27), _15M)
        assert report.is_valid
        assert report.warnings == []
        assert len(report.valid_bars) == 27

    def test_duplicate_timestamps_are_rejected(self):
        moment = _local(date(2026, 8, 18), 10, 15)
        report = validate_intraday_bars([_bar(moment), _bar(moment)], _15M)
        assert [issue.code for issue in report.errors] == [
            "DUPLICATE_TIMESTAMP",
            "DUPLICATE_TIMESTAMP",
        ]
        assert report.valid_bars == []

    def test_an_inconsistent_ohlc_bar_is_rejected(self):
        bad = _bar(
            _local(date(2026, 8, 18), 10, 15),
            open_="42.00",
            high="41.00",
            low="40.00",
            close="42.50",
        )
        report = validate_intraday_bars([bad], _15M)
        assert [issue.code for issue in report.errors] == ["INVALID_OHLC"]

    def test_a_non_positive_price_is_rejected(self):
        report = validate_intraday_bars(
            [_bar(_local(date(2026, 8, 18), 10, 15), close="0")], _15M
        )
        assert [issue.code for issue in report.errors] == ["NON_POSITIVE_PRICE"]

    def test_a_bar_of_the_wrong_size_is_rejected(self):
        """A batch mixing two timeframes is a caller bug, and silently
        splitting it would hide the bug in the data."""
        report = validate_intraday_bars(
            [_bar(_local(date(2026, 8, 18), 10, 15), timeframe=Timeframe.FIVE_MINUTES)],
            _15M,
        )
        assert [issue.code for issue in report.errors] == ["TIMEFRAME_MISMATCH"]

    def test_zero_volume_is_kept(self):
        """The closing print really does come back with volume 0."""
        report = validate_intraday_bars(
            [_bar(_local(date(2026, 8, 18), 17, 0), volume="0")], _15M
        )
        assert report.is_valid
        assert len(report.valid_bars) == 1

    def test_bars_out_of_order_are_flagged_but_kept(self):
        day = date(2026, 8, 18)
        report = validate_intraday_bars(
            [_bar(_local(day, 10, 30)), _bar(_local(day, 10, 15))], _15M
        )
        assert [issue.code for issue in report.warnings] == ["OUT_OF_ORDER"]
        assert len(report.valid_bars) == 2

    def test_an_empty_batch_is_valid_and_empty(self):
        report = validate_intraday_bars([], _15M)
        assert report.is_valid
        assert report.sessions == []


class TestIntraSessionGaps:
    def test_a_hole_between_two_delivered_bars_is_counted(self):
        day = date(2026, 8, 18)
        bars = [
            _bar(_local(day, 10, 15)),
            _bar(_local(day, 10, 30)),
            # 10:45 and 11:00 never arrived.
            _bar(_local(day, 11, 15)),
        ]
        report = validate_intraday_bars(bars, _15M)

        gaps = [issue for issue in report.warnings if issue.code == "INTRA_SESSION_GAP"]
        assert len(gaps) == 1
        assert "2 15m bar(s) missing" in gaps[0].message
        assert report.missing_bars == 2
        assert report.sessions[0].missing_bars == 2

    def test_the_hole_is_a_warning_not_a_rejection(self):
        """A session with a hole is data that says it is holed, not a
        shorter series and not a discarded one."""
        day = date(2026, 8, 18)
        bars = [_bar(_local(day, 10, 15)), _bar(_local(day, 11, 15))]
        report = validate_intraday_bars(bars, _15M)
        assert report.is_valid
        assert len(report.valid_bars) == 2

    def test_the_overnight_boundary_is_not_a_gap(self):
        """Seventeen hours between the last bar of Tuesday and the first
        of Wednesday is the market being closed."""
        bars = _session(date(2026, 8, 18), 27) + _session(date(2026, 8, 19), 27)
        report = validate_intraday_bars(bars, _15M)
        assert [
            issue for issue in report.warnings if issue.code == "INTRA_SESSION_GAP"
        ] == []
        assert report.missing_bars == 0

    def test_coverage_is_reported_for_every_session(self):
        bars = _session(date(2026, 8, 18), 27) + _session(date(2026, 8, 19), 27)
        report = validate_intraday_bars(bars, _15M)
        assert [coverage.session for coverage in report.sessions] == [
            date(2026, 8, 18),
            date(2026, 8, 19),
        ]
        assert report.sessions[0].bar_count == 27
        assert report.sessions[0].first == _local(date(2026, 8, 18), 10, 15)
        assert report.sessions[0].last == _local(date(2026, 8, 18), 16, 45)


class TestShortSessions:
    def _batch(self, counts: dict[date, int]) -> list[IntradayBar]:
        bars: list[IntradayBar] = []
        for day, count in counts.items():
            bars.extend(_session(day, count))
        return bars

    def test_an_interior_session_smaller_than_its_peers_is_flagged(self):
        report = validate_intraday_bars(
            self._batch(
                {
                    date(2026, 8, 17): 27,
                    date(2026, 8, 18): 16,
                    date(2026, 8, 19): 27,
                    date(2026, 8, 20): 27,
                    date(2026, 8, 21): 27,
                }
            ),
            _15M,
        )
        short = [issue for issue in report.warnings if issue.code == "SHORT_SESSION"]
        assert [issue.session for issue in short] == [date(2026, 8, 18)]
        assert "16 bars where the typical session in this batch carries 27" in (
            short[0].message
        )

    def test_the_first_and_last_sessions_are_never_flagged(self):
        """Both are cut by the request window rather than by missing
        data: every vendor range is anchored at the request instant, and
        the newest session may still be trading."""
        report = validate_intraday_bars(
            self._batch(
                {
                    date(2026, 8, 17): 9,
                    date(2026, 8, 18): 27,
                    date(2026, 8, 19): 27,
                    date(2026, 8, 20): 27,
                    date(2026, 8, 21): 5,
                }
            ),
            _15M,
        )
        assert [
            issue for issue in report.warnings if issue.code == "SHORT_SESSION"
        ] == []

    def test_fewer_than_three_sessions_yields_no_comparison(self):
        """With two sessions both are edges, so there is no peer to
        compare against — the same reason the walk-forward refuses to
        average a single fold."""
        report = validate_intraday_bars(
            self._batch({date(2026, 8, 18): 27, date(2026, 8, 19): 4}), _15M
        )
        assert [
            issue for issue in report.warnings if issue.code == "SHORT_SESSION"
        ] == []

    def test_a_longer_session_does_not_make_its_peers_short(self):
        """Modal, not maximum: one session with an extra bar must not
        report every other session as short."""
        report = validate_intraday_bars(
            self._batch(
                {
                    date(2026, 8, 17): 27,
                    date(2026, 8, 18): 27,
                    date(2026, 8, 19): 28,
                    date(2026, 8, 20): 27,
                    date(2026, 8, 21): 27,
                }
            ),
            _15M,
        )
        assert [
            issue for issue in report.warnings if issue.code == "SHORT_SESSION"
        ] == []

    @pytest.mark.parametrize(
        ("counts", "expected"),
        [
            ([27, 27, 16], 27),
            ([27, 16], 27),  # tie broken towards the larger count
            ([16, 16, 27], 16),
        ],
    )
    def test_the_typical_count_is_modal_with_a_spelled_out_tie_break(
        self, counts, expected
    ):
        assert _typical_bar_count(counts) == expected


class TestAbsurdMoves:
    def test_a_violent_move_inside_a_session_is_flagged_but_kept(self):
        day = date(2026, 8, 18)
        bars = [
            _bar(_local(day, 10, 15), close="42.00"),
            _bar(_local(day, 10, 30), close="60.00"),
        ]
        report = validate_intraday_bars(bars, _15M)
        assert [issue.code for issue in report.warnings] == ["ABSURD_MOVE"]
        assert len(report.valid_bars) == 2

    def test_an_overnight_move_is_not_compared(self):
        """A gap between sessions is ordinary market behaviour, and
        comparing across the boundary would flag it every time."""
        bars = [
            _bar(_local(date(2026, 8, 18), 16, 45), close="42.00"),
            _bar(_local(date(2026, 8, 19), 10, 15), close="60.00"),
        ]
        report = validate_intraday_bars(bars, _15M)
        assert [issue for issue in report.warnings if issue.code == "ABSURD_MOVE"] == []


class TestRegressionAgainstRealCapturedBars:
    """PETR4 15-minute bars, captured live on 2026-08-22."""

    # The first four bars of 2026-07-31 as the API returned them: real
    # prices, on a :01/:16/:31/:46 phase, three hours into a session
    # whose peers all start at 10:15 on a :00/:15/:30/:45 phase.
    _REAL_OFF_PHASE: ClassVar[list[tuple[int, str, str, str, str, str]]] = [
        (1785513660, "43.00", "43.08", "42.97", "43.04", "1659000"),
        (1785514560, "43.04", "43.18", "43.04", "43.18", "1051100"),
        (1785515460, "43.18", "43.20", "43.14", "43.16", "640200"),
        (1785516360, "43.16", "43.28", "43.16", "43.25", "782500"),
    ]

    def _off_phase_bars(self) -> list[IntradayBar]:
        return [
            IntradayBar(
                timestamp=datetime.fromtimestamp(epoch, tz=UTC),
                timeframe=_15M,
                open=Decimal(o),
                high=Decimal(h),
                low=Decimal(low),
                close=Decimal(c),
                volume=Decimal(v),
            )
            for epoch, o, h, low, c, v in self._REAL_OFF_PHASE
        ]

    def test_off_phase_bars_are_real_prices_and_are_kept(self):
        """The design decision this test exists to protect: no grid
        alignment check. These sixteen-per-session bars sit on a minute
        phase no other session in the capture uses, and they are real."""
        report = validate_intraday_bars(self._off_phase_bars(), _15M)
        assert report.is_valid
        assert len(report.valid_bars) == 4

    def test_an_off_phase_session_still_has_a_measurable_cadence(self):
        """Consecutive bars are exactly one timeframe apart, so the
        session reports no hole even though it starts late — the late
        start is a `SHORT_SESSION` question, not a gap question."""
        report = validate_intraday_bars(self._off_phase_bars(), _15M)
        assert report.missing_bars == 0
        assert report.sessions[0].session == date(2026, 7, 31)
        assert report.sessions[0].bar_count == 4

    def test_the_capture_puts_that_session_at_13_01_local(self):
        report = validate_intraday_bars(self._off_phase_bars(), _15M)
        first_local = report.sessions[0].first.astimezone(EXCHANGE_TIMEZONE)
        assert (first_local.hour, first_local.minute) == (13, 1)
