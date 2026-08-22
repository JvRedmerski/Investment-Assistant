"""Data quality for a series of intraday bars (AGENTS.md rules 19, 20).

Sibling of `data_quality.py`, which does the same job for daily bars, and
deliberately not an extension of it. A daily series is keyed by a date and
has no notion of a session; an intraday series is a sequence of sessions,
and almost everything interesting about its quality is a statement about
one session or about how the sessions compare to each other.

Pure and deterministic, no I/O (rule 68).

## What a gap is, and what this refuses to pretend a gap is

A **measured** gap is a hole between two bars that were actually
delivered inside one session: two consecutive bars more than one
`timeframe` apart have something missing between them, and how much is
arithmetic. That claim needs no calendar and no assumption.

What cannot be measured the same way is a session's **edges**. Nothing in
a response says when trading opened; the first bar delivered is simply
the first bar delivered. Deciding it arrived late would require knowing
B3's session hours for that date, which this project does not have and
the source does not publish — and guessing would be exactly the
heuristic-dressed-as-measurement that ADR-023 rejected.

So a short session is reported **relative to its peers in the same
batch**, never against an assumed timetable: *this session carries 16
bars where the typical session in this batch carries 27*. That statement
is true whether the exchange opened late, halted, or the vendor lost
rows, and it does not claim to know which.

## What this deliberately does not check

**Grid alignment.** It is tempting to require that 15-minute bars land on
:00/:15/:30/:45, and it would have been wrong: in the captured PETR4
history, 2026-07-31's bars sit on :01/:16/:31/:46 while all twenty-one
other sessions sit on the clean phase. Those sixteen bars are real
prices. A phase check would have rejected every one of them and called a
genuinely short session a malformed one instead.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from itertools import pairwise

from app.integrations.market_data.schemas import IntradayBar, Timeframe

#: B3's offset from UTC, as a fixed offset rather than an IANA zone.
#:
#: The decision and its boundary (ADR-037): Brazil abolished daylight
#: saving in 2019, so the offset has been a constant -03:00 for every
#: date this project can reach — the vendor serves at most three months
#: of intraday history. `ZoneInfo("America/Sao_Paulo")` would encode the
#: rule rather than the constant, but it needs an IANA database that
#: Windows does not ship: it raises `ZoneInfoNotFoundError` on the
#: development machine here while working inside the Linux container,
#: so the same code would group sessions differently depending on where
#: it ran. A fixed offset behaves identically everywhere and is honest
#: about what it claims.
#:
#: What would invalidate it: Brazil reinstating DST, or this project
#: acquiring pre-2019 intraday history. Either means replacing this
#: constant with a real zone and taking the `tzdata` dependency.
EXCHANGE_UTC_OFFSET = timedelta(hours=-3)
EXCHANGE_TIMEZONE = timezone(EXCHANGE_UTC_OFFSET, "B3")

#: A within-session bar-to-bar move beyond this fraction is flagged, not
#: rejected. Lower than the daily 50% because a minute is not a day, and
#: still a heuristic rather than a rule — a single stock can genuinely
#: move this much in one bar on news. Compared only *inside* a session:
#: across an overnight boundary an ordinary gap would trip it every time.
ABSURD_INTRADAY_MOVE_THRESHOLD = Decimal("0.20")


def session_date(moment: datetime) -> date:
    """Which trading session an instant belongs to.

    A local-market question, so it is answered in local time. Grouping
    by the UTC date happens to give the same answer for B3 today, since
    the whole session sits inside one UTC day — but that is a
    coincidence of the offset, not a property of sessions, and it would
    stop being true for any market that trades across UTC midnight.
    """
    return moment.astimezone(EXCHANGE_TIMEZONE).date()


@dataclass
class IntradayIssue:
    session: date
    #: The bar the issue is about, or `None` when the issue is about the
    #: session as a whole (a short session is not any one bar's fault).
    at: datetime | None
    code: str
    message: str


@dataclass
class SessionCoverage:
    """What one session actually delivered.

    Reported for every session in the batch, clean or not, because
    "what have I got" is the question a caller asks before "what is
    wrong with it". `missing_bars` counts only holes **between**
    delivered bars — never the unknown amount before the first or after
    the last.
    """

    session: date
    bar_count: int
    first: datetime
    last: datetime
    missing_bars: int = 0


@dataclass
class IntradayQualityReport:
    timeframe: Timeframe
    valid_bars: list[IntradayBar] = field(default_factory=list)
    sessions: list[SessionCoverage] = field(default_factory=list)
    errors: list[IntradayIssue] = field(default_factory=list)
    warnings: list[IntradayIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def rejected_count(self) -> int:
        # One error per rejected bar, except SHORT_SESSION which is a
        # warning, so this matches how many input bars were dropped.
        return len(self.errors)

    @property
    def missing_bars(self) -> int:
        """Bars known to be missing inside the sessions delivered."""
        return sum(coverage.missing_bars for coverage in self.sessions)


def validate_intraday_bars(
    bars: list[IntradayBar], timeframe: Timeframe
) -> IntradayQualityReport:
    """Validate one asset's intraday bars for one timeframe.

    `timeframe` is passed explicitly rather than read off the bars: an
    empty batch has none to read, and a batch that mixes two sizes is a
    caller bug that should be named rather than silently split.

    Input order is not assumed to be chronological. `valid_bars` keeps
    the input's order; the session analysis sorts internally.
    """
    report = IntradayQualityReport(timeframe=timeframe)

    counts = Counter(bar.timestamp for bar in bars)
    duplicates = {stamp for stamp, count in counts.items() if count > 1}

    if _is_out_of_order(bars):
        report.warnings.append(
            IntradayIssue(
                session=session_date(bars[0].timestamp),
                at=None,
                code="OUT_OF_ORDER",
                message="Bars were not provided in chronological order.",
            )
        )

    accepted: list[IntradayBar] = []
    for bar in bars:
        error = _validate_single_bar(bar, timeframe, duplicates)
        if error is not None:
            report.errors.append(error)
            continue
        accepted.append(bar)

    report.valid_bars = accepted
    report.sessions = _analyse_sessions(accepted, timeframe, report.warnings)
    _flag_short_sessions(report.sessions, report.warnings)
    return report


def _validate_single_bar(
    bar: IntradayBar, timeframe: Timeframe, duplicates: set[datetime]
) -> IntradayIssue | None:
    session = session_date(bar.timestamp)

    if bar.timeframe is not timeframe:
        return IntradayIssue(
            session=session,
            at=bar.timestamp,
            code="TIMEFRAME_MISMATCH",
            message=(
                f"Bar at {bar.timestamp.isoformat()} is a {bar.timeframe.value} "
                f"bar in a {timeframe.value} batch."
            ),
        )

    if bar.timestamp in duplicates:
        return IntradayIssue(
            session=session,
            at=bar.timestamp,
            code="DUPLICATE_TIMESTAMP",
            message=(
                f"Timestamp {bar.timestamp.isoformat()} appears more than once "
                f"in the batch."
            ),
        )

    if any(price <= 0 for price in (bar.open, bar.high, bar.low, bar.close)):
        return IntradayIssue(
            session=session,
            at=bar.timestamp,
            code="NON_POSITIVE_PRICE",
            message=f"Bar at {bar.timestamp.isoformat()} has a zero or negative price.",
        )

    # Rule 20's OHLC example. Volume is deliberately not required to be
    # positive: the closing print comes back with volume 0, and it is a
    # bar the exchange published rather than a malformed one.
    if not (
        bar.low <= bar.high
        and bar.low <= bar.open
        and bar.low <= bar.close
        and bar.high >= bar.open
        and bar.high >= bar.close
    ):
        return IntradayIssue(
            session=session,
            at=bar.timestamp,
            code="INVALID_OHLC",
            message=(
                f"Bar at {bar.timestamp.isoformat()} has inconsistent OHLC "
                f"(open={bar.open}, high={bar.high}, low={bar.low}, "
                f"close={bar.close})."
            ),
        )

    return None


def _analyse_sessions(
    bars: list[IntradayBar],
    timeframe: Timeframe,
    warnings: list[IntradayIssue],
) -> list[SessionCoverage]:
    """Per-session coverage, plus the holes and jumps found inside each."""
    grouped: dict[date, list[IntradayBar]] = {}
    for bar in bars:
        grouped.setdefault(session_date(bar.timestamp), []).append(bar)

    step = timeframe.seconds
    coverages: list[SessionCoverage] = []

    for session in sorted(grouped):
        ordered = sorted(grouped[session], key=lambda b: b.timestamp)
        missing = 0

        for previous, current in pairwise(ordered):
            elapsed = int((current.timestamp - previous.timestamp).total_seconds())
            if elapsed > step:
                absent = elapsed // step - 1
                missing += absent
                warnings.append(
                    IntradayIssue(
                        session=session,
                        at=previous.timestamp,
                        code="INTRA_SESSION_GAP",
                        message=(
                            f"{absent} {timeframe.value} bar(s) missing between "
                            f"{previous.timestamp.astimezone(EXCHANGE_TIMEZONE):%H:%M} "
                            f"and "
                            f"{current.timestamp.astimezone(EXCHANGE_TIMEZONE):%H:%M}."
                        ),
                    )
                )

            if previous.close > 0:
                move = abs(current.close - previous.close) / previous.close
                if move > ABSURD_INTRADAY_MOVE_THRESHOLD:
                    warnings.append(
                        IntradayIssue(
                            session=session,
                            at=current.timestamp,
                            code="ABSURD_MOVE",
                            message=(
                                f"Close moved {move:.0%} within the session "
                                f"({previous.close} -> {current.close})."
                            ),
                        )
                    )

        coverages.append(
            SessionCoverage(
                session=session,
                bar_count=len(ordered),
                first=ordered[0].timestamp,
                last=ordered[-1].timestamp,
                missing_bars=missing,
            )
        )

    return coverages


def _flag_short_sessions(
    coverages: list[SessionCoverage], warnings: list[IntradayIssue]
) -> None:
    """Compare each interior session's size against the batch's typical one.

    The first and last sessions are excluded from both the comparison and
    the reference, because both are cut by something that is not missing
    data: every vendor range is anchored at the request instant, so the
    oldest session in a batch starts wherever the window happened to
    begin, and the newest may still be trading. Measured on the capture:
    a one-day window of one-minute bars opened at 10:19 purely because
    that was 24 hours before the request.

    Fewer than three sessions therefore yields nothing, by construction —
    the same reason the walk-forward refuses to average one fold.
    """
    if len(coverages) < 3:
        return

    interior = coverages[1:-1]
    typical = _typical_bar_count([coverage.bar_count for coverage in interior])

    for coverage in interior:
        if coverage.bar_count < typical:
            warnings.append(
                IntradayIssue(
                    session=coverage.session,
                    at=None,
                    code="SHORT_SESSION",
                    message=(
                        f"Session carries {coverage.bar_count} bars where the "
                        f"typical session in this batch carries {typical}."
                    ),
                )
            )


def _typical_bar_count(counts: list[int]) -> int:
    """The modal bar count, ties broken towards the larger count.

    Modal rather than maximum: one session with an extra bar would make
    every other session look short. The tie-break is spelled out so the
    result does not depend on dictionary ordering (rule 113).
    """
    frequencies = Counter(counts)
    best_frequency = max(frequencies.values())
    return max(count for count, freq in frequencies.items() if freq == best_frequency)


def _is_out_of_order(bars: list[IntradayBar]) -> bool:
    return any(
        bars[index].timestamp > bars[index + 1].timestamp
        for index in range(len(bars) - 1)
    )
