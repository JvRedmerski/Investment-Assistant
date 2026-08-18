"""Data quality checks for a benchmark series (AGENTS.md rule 20).

The counterpart of `market_data.data_quality`, and it lives in the domain
layer rather than beside the providers for one reason: every check here
needs the `BenchmarkDefinition` — the kind decides what a valid value
even is, and the periodicity decides when an observation is finished.
`validate_daily_bars` needs nothing but the bar, so it stays in
integrations.

Pydantic (`BenchmarkObservation`) already guarantees a well-formed date
and `Decimal`. What it cannot see is invalidity across a *series*:
duplicate dates, an observation the source listed without a figure, a
value that cannot be what it claims to be, or a period that has not
finished yet.

## The check that matters most: `INCOMPLETE_PERIOD`

Ingestion never rewrites a stored date (see `service.sync_benchmark_series`),
which makes storing a not-yet-final figure permanent. That is not
hypothetical: Brapi's `historicalDataPrice` includes the **session in
progress** as though it were a closed bar, and two requests 2.5 minutes
apart on 2026-08-18 returned 166851.5156 and 166978.9375 for that same
date. Whichever arrived first would have been frozen in as the Ibovespa's
close.

ADR-016 established the answer for exactly this shape of problem: reject,
do not store, and let the next sync insert the real figure. The cost is
that the latest period shows up about a day late; the benefit is that no
stored value is ever a snapshot of something still moving.

An observation is complete when its **period** has ended, which is why
periodicity is needed and a date comparison alone will not do. The IPCA
observation dated 2026-08-01 measures all of August, so on 2026-08-18 it
is a third of a month old, not seventeen days settled.

## What is a warning rather than an error

A rejected observation is one that cannot be stored truthfully. Anything
that is merely *surprising* is stored with a warning, because Brazilian
series contain real extremes — monthly inflation genuinely exceeded 80%
in 1990 — and a validator that quietly truncated that history would be
worse than one that flagged it.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.domain.benchmarks.catalog import BenchmarkDefinition
from app.integrations.benchmarks.schemas import BenchmarkKind, BenchmarkObservation
from app.quant.returns import Periodicity

#: A single-period move beyond this fraction, for an `INDEX`, is flagged.
#:
#: Same threshold and same rationale as `ABSURD_MOVE_THRESHOLD` in the
#: market data checks: a headline index moving more than half its value
#: in one session is far more likely a data error than a market event,
#: but 1998 and 2020 argue against rejecting it outright.
ABSURD_MOVE_THRESHOLD = Decimal("0.5")

#: Per-period rate magnitude beyond which a `RATE` observation is flagged.
#:
#: Heuristics, tuned to the periodicity because the same number means
#: wildly different things: 1% in a day is roughly 1,100% a year, while
#: 1% in a month is an ordinary Brazilian inflation print. The monthly
#: bound is set at 20% so the hyperinflation years warn — they should be
#: looked at — without being thrown away.
ABSURD_RATE_THRESHOLD: dict[Periodicity, Decimal] = {
    Periodicity.DAILY: Decimal("0.01"),
    Periodicity.WEEKLY: Decimal("0.05"),
    Periodicity.MONTHLY: Decimal("0.20"),
    Periodicity.QUARTERLY: Decimal("0.50"),
    Periodicity.YEARLY: Decimal("1.00"),
}


@dataclass
class ObservationIssue:
    observation_date: date
    code: str
    message: str


@dataclass
class BenchmarkQualityReport:
    valid_observations: list[BenchmarkObservation] = field(default_factory=list)
    errors: list[ObservationIssue] = field(default_factory=list)
    warnings: list[ObservationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def rejected_count(self) -> int:
        # One error per rejected observation, so this is how many of the
        # inputs were dropped.
        return len(self.errors)


def validate_benchmark_series(
    observations: list[BenchmarkObservation],
    definition: BenchmarkDefinition,
    today: date,
) -> BenchmarkQualityReport:
    """Separate the observations safe to store from the ones that are not.

    `today` is passed in rather than read from a clock, so the function
    stays pure and every boundary case is reachable from a test (AGENTS.md
    rule 68). An observation is rejected as incomplete when its period has
    not ended *before* `today`; a period ending on `today` is still
    running.
    """
    report = BenchmarkQualityReport()

    seen: dict[date, int] = {}
    for observation in observations:
        seen[observation.date] = seen.get(observation.date, 0) + 1
    duplicates = {day for day, count in seen.items() if count > 1}

    if _is_out_of_order(observations):
        report.warnings.append(
            ObservationIssue(
                observation_date=observations[0].date if observations else date.min,
                code="OUT_OF_ORDER",
                message="Observations were not provided in chronological order.",
            )
        )

    accepted: list[BenchmarkObservation] = []
    for observation in observations:
        error = _validate_single(observation, definition, duplicates, today)
        if error is not None:
            report.errors.append(error)
            continue
        accepted.append(observation)

    report.warnings.extend(_surprising(accepted, definition))
    report.valid_observations = accepted
    return report


def _validate_single(
    observation: BenchmarkObservation,
    definition: BenchmarkDefinition,
    duplicates: set[date],
    today: date,
) -> ObservationIssue | None:
    if observation.date in duplicates:
        return ObservationIssue(
            observation_date=observation.date,
            code="DUPLICATE_DATE",
            message=f"Date {observation.date} appears more than once in the batch.",
        )

    if observation.value is None:
        return ObservationIssue(
            observation_date=observation.date,
            code="MISSING_VALUE",
            message=(
                f"{definition.code} has no value reported for "
                f"{observation.date}; storing it would require inventing one."
            ),
        )

    period_end = period_end_for(observation.date, definition.periodicity)
    if period_end >= today:
        return ObservationIssue(
            observation_date=observation.date,
            code="INCOMPLETE_PERIOD",
            message=(
                f"The {definition.periodicity.value.lower()} period dated "
                f"{observation.date} runs through {period_end} and has not "
                f"finished as of {today}; its value can still change."
            ),
        )

    if definition.kind is BenchmarkKind.INDEX and observation.value <= 0:
        return ObservationIssue(
            observation_date=observation.date,
            code="NON_POSITIVE_LEVEL",
            message=(
                f"{definition.code} reported a zero or negative level "
                f"({observation.value}) for {observation.date}."
            ),
        )

    if definition.kind is BenchmarkKind.RATE and observation.value <= -1:
        # A rate of -100% or worse would take an accumulated index to zero
        # or through it, making every subsequent return undefined or
        # sign-flipped. Deflation is legitimate and stays accepted; this
        # bound is only about arithmetic that cannot mean anything.
        return ObservationIssue(
            observation_date=observation.date,
            code="IMPOSSIBLE_RATE",
            message=(
                f"{definition.code} reported a rate of {observation.value} "
                f"for {observation.date}, at or below -100%."
            ),
        )

    return None


def _surprising(
    accepted: list[BenchmarkObservation], definition: BenchmarkDefinition
) -> list[ObservationIssue]:
    """Warnings for stored-but-noteworthy observations."""
    issues: list[ObservationIssue] = []
    ordered = sorted(accepted, key=lambda observation: observation.date)

    if definition.kind is BenchmarkKind.RATE:
        threshold = ABSURD_RATE_THRESHOLD[definition.periodicity]
        for observation in ordered:
            assert observation.value is not None  # rejected above otherwise
            if abs(observation.value) > threshold:
                issues.append(
                    ObservationIssue(
                        observation_date=observation.date,
                        code="ABSURD_RATE",
                        message=(
                            f"{definition.code} of {observation.value:.6f} for "
                            f"{observation.date} exceeds the {threshold} "
                            f"per-period sanity bound."
                        ),
                    )
                )
        return issues

    previous: BenchmarkObservation | None = None
    for observation in ordered:
        assert observation.value is not None  # rejected above otherwise
        if previous is not None and previous.value:
            move = abs(observation.value - previous.value) / previous.value
            if move > ABSURD_MOVE_THRESHOLD:
                issues.append(
                    ObservationIssue(
                        observation_date=observation.date,
                        code="ABSURD_MOVE",
                        message=(
                            f"{definition.code} moved {move:.0%} from the "
                            f"previous observation ({previous.value} -> "
                            f"{observation.value})."
                        ),
                    )
                )
        previous = observation
    return issues


def period_end_for(day: date, periodicity: Periodicity) -> date:
    """The last calendar day of the period `day` falls in.

    Public because ingestion reports it and tests assert on it. Uses the
    ISO week, matching `period_returns`, so a week straddling New Year is
    one period in both places.
    """
    if periodicity is Periodicity.DAILY:
        return day
    if periodicity is Periodicity.WEEKLY:
        return day + timedelta(days=7 - day.isoweekday())
    if periodicity is Periodicity.MONTHLY:
        return _last_day_of_month(day.year, day.month)
    if periodicity is Periodicity.QUARTERLY:
        final_month = ((day.month - 1) // 3 + 1) * 3
        return _last_day_of_month(day.year, final_month)
    if periodicity is Periodicity.YEARLY:
        return date(day.year, 12, 31)
    raise ValueError(f"Unsupported periodicity: {periodicity}")


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _is_out_of_order(observations: list[BenchmarkObservation]) -> bool:
    return any(
        observations[index].date > observations[index + 1].date
        for index in range(len(observations) - 1)
    )
