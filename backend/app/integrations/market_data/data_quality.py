"""Data quality checks for a series of daily OHLCV bars (AGENTS.md rule 20).

Pydantic (`schemas.DailyBar`) already guarantees every field is present
and is a well-formed `Decimal` (rule 19 — never assume a field exists).
What it cannot catch is business-level invalidity across a *series* of
bars: a negative/zero price, an internally inconsistent OHLC bar,
duplicate dates, bars given out of chronological order, or a
day-over-day move so large it is more likely a data error than a real
price. That is this module's job.

It also enforces one storage invariant: every bar in `valid_bars` has an
`adjusted_close` the source actually reported. Callers may therefore
store it into the `NOT NULL` column without a further check.

This is a small, pure, deterministic function with no I/O (AGENTS.md rule
68 — testable with known input/output), so it can be unit tested in
isolation and reused wherever bars need validating before being trusted.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.integrations.market_data.schemas import DailyBar

# A single-day close-to-close move beyond this fraction is flagged as a
# warning, not rejected: real stock splits, composite/ex-dividend events,
# or genuinely volatile trading days can legitimately move this much.
# This is a heuristic, not a hard rule — document the threshold if tuned.
ABSURD_MOVE_THRESHOLD = Decimal("0.5")  # 50%


@dataclass
class BarIssue:
    bar_date: date
    code: str
    message: str


@dataclass
class DataQualityReport:
    valid_bars: list[DailyBar] = field(default_factory=list)
    errors: list[BarIssue] = field(default_factory=list)
    warnings: list[BarIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def rejected_count(self) -> int:
        # One error per rejected bar (see _validate_single_bar), so this
        # matches how many of the input bars were dropped.
        return len(self.errors)


def validate_daily_bars(bars: list[DailyBar]) -> DataQualityReport:
    """Validate a batch of daily bars for one asset.

    Returns a report separating bars safe to store (`valid_bars`) from
    the ones rejected (`errors`) and the ones stored but worth flagging
    (`warnings`). Input order is not assumed to be chronological; the
    report itself does not reorder `valid_bars` relative to the input.
    """
    report = DataQualityReport()

    dates_seen: dict[date, int] = {}
    for bar in bars:
        dates_seen[bar.date] = dates_seen.get(bar.date, 0) + 1
    duplicate_dates = {d for d, count in dates_seen.items() if count > 1}

    if _is_out_of_order(bars):
        report.warnings.append(
            BarIssue(
                bar_date=bars[0].date if bars else date.min,
                code="OUT_OF_ORDER",
                message="Bars were not provided in chronological order.",
            )
        )

    accepted: list[DailyBar] = []
    for bar in bars:
        error = _validate_single_bar(bar, duplicate_dates)
        if error is not None:
            report.errors.append(error)
            continue
        accepted.append(bar)

    accepted_sorted = sorted(accepted, key=lambda b: b.date)
    previous: DailyBar | None = None
    for bar in accepted_sorted:
        if previous is not None and previous.close > 0:
            move = abs(bar.close - previous.close) / previous.close
            if move > ABSURD_MOVE_THRESHOLD:
                report.warnings.append(
                    BarIssue(
                        bar_date=bar.date,
                        code="ABSURD_MOVE",
                        message=(
                            f"Close moved {move:.0%} from the previous bar "
                            f"({previous.close} -> {bar.close})."
                        ),
                    )
                )
        previous = bar

    report.valid_bars = accepted
    return report


def _validate_single_bar(bar: DailyBar, duplicate_dates: set[date]) -> BarIssue | None:
    if bar.date in duplicate_dates:
        return BarIssue(
            bar_date=bar.date,
            code="DUPLICATE_DATE",
            message=f"Date {bar.date} appears more than once in the batch.",
        )

    # A bar the source did not adjust is not storable. Returns are
    # computed from `adjusted_close` (Wave 07), and `adjusted_close` is
    # `NOT NULL`, so the only alternatives would be to fabricate it from
    # `close` — forbidden by rule 44 / ADR-014 — or to store a wrong
    # number permanently, since `sync_daily_history` never rewrites a
    # stored date. Rejecting leaves the date absent instead, and a later
    # sync inserts it once the source publishes the adjustment. In
    # practice this defers only the most recently closed session.
    if bar.adjusted_close is None:
        return BarIssue(
            bar_date=bar.date,
            code="MISSING_ADJUSTED_CLOSE",
            message=(
                f"Bar for {bar.date} has no adjusted close reported by the "
                f"source; storing it would require fabricating one."
            ),
        )

    prices = (bar.open, bar.high, bar.low, bar.close, bar.adjusted_close)
    if any(price <= 0 for price in prices):
        return BarIssue(
            bar_date=bar.date,
            code="NON_POSITIVE_PRICE",
            message=f"Bar for {bar.date} has a zero or negative price.",
        )

    if bar.volume < 0:
        return BarIssue(
            bar_date=bar.date,
            code="INVALID_VOLUME",
            message=f"Bar for {bar.date} has negative volume.",
        )

    # AGENTS.md rule 20 OHLC example: low <= open, low <= close,
    # high >= open, high >= close (and low <= high, implied but checked
    # explicitly for a clearer error message).
    if not (
        bar.low <= bar.high
        and bar.low <= bar.open
        and bar.low <= bar.close
        and bar.high >= bar.open
        and bar.high >= bar.close
    ):
        return BarIssue(
            bar_date=bar.date,
            code="INVALID_OHLC",
            message=(
                f"Bar for {bar.date} has inconsistent OHLC "
                f"(open={bar.open}, high={bar.high}, low={bar.low}, close={bar.close})."
            ),
        )

    return None


def _is_out_of_order(bars: list[DailyBar]) -> bool:
    return any(bars[i].date > bars[i + 1].date for i in range(len(bars) - 1))
