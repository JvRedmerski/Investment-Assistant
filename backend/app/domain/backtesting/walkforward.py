"""Choosing parameters on history the choice is never judged on.

The I/O half of Wave 14. `folds` decides which periods exist, `grid`
decides which policies may be tried, `objectives` decides what a segment
is worth — this module runs the backtests and puts the three together.

Nothing new is measured here. Every segment is a `run_backtest` over the
same universe with a different policy and a different span, so a fold is
measured by exactly the code that measures the investor's own portfolio,
which is the whole reason W13 refused to keep a second set of books.

## What the three segments each do, and why they cannot be swapped

- **Train** asks every candidate in the grid. Seven runs, one question
  each.
- **Validation** asks only the shortlist, on history the ranking never
  saw. It exists because the best candidate on one period is very often
  the best *fit to that period*, and one step forward is the cheapest
  test of whether the answer survives at all.
- **Test** runs the winner and nothing else. **No figure measured here
  ever reaches a selection.** That is the whole of rule 61, and the only
  reason an out-of-sample number means anything.

Test is always the latest of the three, so nothing chosen could have been
chosen with knowledge of it (rule 58, and the same discipline `simulation`
enforces inside a single run).

## Every segment run starts from an empty portfolio

Deliberate, and the reason `folds` makes the three segments the same
length. A run inherits nothing: same starting cash, same absent
positions, same span. Candidates are then comparable to each other, and
in-sample is comparable to out-of-sample, because the only things that
differ are the policy and the period.

⚠️ **The cost is real and is not hidden**: a segment measures the
strategy *accumulating*, not the strategy running on a mature portfolio.
The Diversification pillar reads an empty portfolio on the first
contribution of every segment, so a walk-forward here evaluates the
allocator's early behaviour. Carrying the portfolio across the boundary
would fix that and break the comparison instead — the test segment would
inherit whatever the selected candidate happened to buy, and in-sample
and out-of-sample would stop being the same experiment.

## What is reported, and what is refused

A fold reports the ranking, the shortlist, the winner and the winner's
out-of-sample result, plus the **degradation**: what it scored on
validation less what it scored on test. That figure is the point. A
strategy whose out-of-sample result matches its in-sample one has
parameters that describe something; one that collapses has parameters
that described the sample.

Stability is across folds — how often the same candidate won, and how far
the out-of-sample figures sit from each other. With a single fold there
is nothing to compare, so it is `SINGLE_FOLD` and the aggregates are
absent rather than a mean of one and a spread of zero. A spread of zero
would read as *perfectly stable*, which is the exact opposite of what one
observation supports.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models.assets import Asset
from app.domain.backtesting.availability import PUBLICATION_LAG_MONTHS
from app.domain.backtesting.folds import (
    DEFAULT_SCHEME,
    Fold,
    Partition,
    Segment,
    WalkForwardScheme,
    partition,
)
from app.domain.backtesting.grid import (
    WALK_FORWARD_GRID_VERSION,
    PolicyCandidate,
    policy_grid,
)
from app.domain.backtesting.objectives import (
    OBJECTIVE_UNAVAILABLE,
    SegmentMetrics,
    SelectionObjective,
    measure_segment,
    objective_value,
)
from app.domain.backtesting.service import (
    DEFAULT_COSTS,
    BacktestSettings,
    BacktestWindow,
    run_backtest,
    testable_universe,
)
from app.domain.backtesting.simulation import ZERO, CostModel
from app.domain.benchmarks.service import risk_free_rate_for
from app.domain.recommendations.allocation import DEFAULT_POLICY, AllocationPolicy
from app.quant.risk import standard_deviation

#: How many of the trained candidates go forward to validation.
#:
#: Three: enough that the train winner is not simply confirmed by
#: itself, few enough that validation stays a check rather than a second
#: sweep. Passing the whole grid forward would make validation a second
#: training set, which is the thing rule 61 separates them to prevent.
SHORTLIST = 3

#: One fold is not a sample. Reported instead of a mean of one.
SINGLE_FOLD = "SINGLE_FOLD"

#: Nothing could be replayed at all — no asset survived the universe
#: filter, so there is no history to partition.
NOTHING_TESTABLE = "NOTHING_TESTABLE"


@dataclass(frozen=True)
class WalkForwardSettings:
    """Everything a walk-forward is parameterised by (rule 113).

    The backtest half is `BacktestSettings` minus the window, which the
    partition supplies per segment. `policy` is the **base** the grid
    varies from, not a policy that will be run as given — though it is,
    as the grid's first candidate.
    """

    start: date
    end: date
    strategy: str
    contribution: Decimal
    day_of_month: int = 1
    costs: CostModel = DEFAULT_COSTS
    policy: AllocationPolicy = DEFAULT_POLICY
    publication_lag_months: int = PUBLICATION_LAG_MONTHS
    scheme: WalkForwardScheme = DEFAULT_SCHEME
    objective: SelectionObjective = SelectionObjective.SHARPE
    shortlist: int = SHORTLIST


@dataclass(frozen=True)
class SegmentOutcome:
    """One policy over one segment: what the series says and what it cost.

    `objective` is the single figure the fold ranks on, lifted out of
    `metrics` so a reader can see which number decided without having to
    know which enum was passed. `None` means unrankable, never worst.
    """

    metrics: SegmentMetrics
    objective: Decimal | None
    trades: int
    fees: Decimal
    slippage: Decimal
    contributed: Decimal
    final_value: Decimal | None


@dataclass(frozen=True)
class CandidateRun:
    """One grid candidate, over one segment."""

    name: str
    question: str
    policy: AllocationPolicy
    outcome: SegmentOutcome


@dataclass(frozen=True)
class FoldResult:
    """One `Train → Validate → Test`, and what survived it.

    `refusal` is set when no candidate could be scored at all — the
    objective was not computable on any of them, which on the default
    objective means no CDI was ingested for the segment. The fold is then
    reported with its runs and without a winner, rather than with a
    winner picked by a fallback nobody asked for.
    """

    index: int
    train: Segment
    validation: Segment
    test: Segment
    trained: tuple[CandidateRun, ...]
    shortlist: tuple[str, ...]
    validated: tuple[CandidateRun, ...]
    selected: str | None
    tested: SegmentOutcome | None
    #: What the winner scored on validation — the number that chose it.
    in_sample: Decimal | None
    #: What it scored on test, which chose nothing.
    out_of_sample: Decimal | None
    #: `in_sample - out_of_sample`. Positive means the choice did worse
    #: on history it had not seen, which is what overfitting looks like.
    degradation: Decimal | None
    refusal: str | None = None


@dataclass(frozen=True)
class Stability:
    """What the folds agree on, or the named reason they cannot say.

    Rule 62 asks for the strategy to be evaluated *for stability*, which
    is a statement about repetition and not about any single fold. So
    every aggregate here is absent when there is one fold, and the fold's
    own out-of-sample figure is left to speak for itself.
    """

    folds: int
    measured_folds: int
    #: How many folds each candidate won, by name.
    selections: dict[str, int]
    most_selected: str | None
    #: Fraction of measured folds the most selected candidate won. A
    #: walk-forward that picks a different winner every time has found
    #: noise, not a parameter.
    selection_rate: Decimal | None
    out_of_sample_mean: Decimal | None
    out_of_sample_min: Decimal | None
    out_of_sample_max: Decimal | None
    out_of_sample_stdev: Decimal | None
    degradation_mean: Decimal | None
    #: Folds whose out-of-sample objective came out above zero.
    positive_folds: int | None
    refusal: str | None = None


@dataclass(frozen=True)
class WalkForwardResult:
    """One walk-forward, with everything needed to read it and repeat it."""

    settings: WalkForwardSettings
    grid_version: str
    window: BacktestWindow
    universe: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]
    candidates: tuple[PolicyCandidate, ...]
    partition: Partition
    folds: tuple[FoldResult, ...]
    stability: Stability


def run_walk_forward(
    db: Session,
    assets: Sequence[Asset],
    settings: WalkForwardSettings,
) -> WalkForwardResult:
    """Partition the replayable history and walk the strategy through it."""
    scope = testable_universe(db, assets, settings.start, settings.end)
    closing = (
        min(settings.end, scope.last_session)
        if scope.last_session is not None
        else settings.end
    )
    window = BacktestWindow(
        requested_start=settings.start,
        requested_end=settings.end,
        start=scope.start,
        end=closing,
        bounded_by=scope.bounded_by,
    )
    grid = policy_grid(settings.policy)

    if not scope.assets:
        return _empty(settings, window, scope.excluded, grid, NOTHING_TESTABLE)

    layout = partition(window.start, window.end, settings.scheme)
    folds = tuple(
        _run_fold(db, scope.assets, settings, grid, fold) for fold in layout.folds
    )

    return WalkForwardResult(
        settings=settings,
        grid_version=WALK_FORWARD_GRID_VERSION,
        window=window,
        universe=tuple(asset.ticker for asset in scope.assets),
        excluded=scope.excluded,
        candidates=grid,
        partition=layout,
        folds=folds,
        stability=_stability(folds, layout),
    )


# -- one fold ---------------------------------------------------------


def _run_fold(
    db: Session,
    assets: Sequence[Asset],
    settings: WalkForwardSettings,
    grid: Sequence[PolicyCandidate],
    fold: Fold,
) -> FoldResult:
    """Rank on train, choose on validation, report on test."""
    trained = tuple(
        _run_candidate(db, assets, settings, candidate, fold.train)
        for candidate in grid
    )
    ranked = _ranked(trained)
    shortlist = tuple(run.name for run in ranked[: settings.shortlist])

    if not shortlist:
        return _unselected(fold, trained, OBJECTIVE_UNAVAILABLE)

    by_name = {candidate.name: candidate for candidate in grid}
    validated = tuple(
        _run_candidate(db, assets, settings, by_name[name], fold.validation)
        for name in shortlist
    )
    confirmed = _ranked(validated)
    if not confirmed:
        return _unselected(fold, trained, OBJECTIVE_UNAVAILABLE, shortlist, validated)

    winner = confirmed[0]
    tested = _run_candidate(
        db, assets, settings, by_name[winner.name], fold.test
    ).outcome

    in_sample = winner.outcome.objective
    out_of_sample = tested.objective
    return FoldResult(
        index=fold.index,
        train=fold.train,
        validation=fold.validation,
        test=fold.test,
        trained=trained,
        shortlist=shortlist,
        validated=validated,
        selected=winner.name,
        tested=tested,
        in_sample=in_sample,
        out_of_sample=out_of_sample,
        degradation=(
            in_sample - out_of_sample
            if in_sample is not None and out_of_sample is not None
            else None
        ),
    )


def _run_candidate(
    db: Session,
    assets: Sequence[Asset],
    settings: WalkForwardSettings,
    candidate: PolicyCandidate,
    segment: Segment,
) -> CandidateRun:
    """Replay one policy over one segment, from an empty portfolio."""
    result = run_backtest(
        db,
        assets,
        BacktestSettings(
            start=segment.start,
            end=segment.end,
            strategy=settings.strategy,
            contribution=settings.contribution,
            day_of_month=settings.day_of_month,
            costs=settings.costs,
            policy=candidate.policy,
            publication_lag_months=settings.publication_lag_months,
        ),
    )

    metrics = measure_segment(
        list(result.index),
        risk_free_rate_for(db, segment.start, segment.end),
        segment.end,
    )
    final = result.final
    return CandidateRun(
        name=candidate.name,
        question=candidate.question,
        policy=candidate.policy,
        outcome=SegmentOutcome(
            metrics=metrics,
            objective=objective_value(metrics, settings.objective),
            trades=result.trades.trades,
            fees=result.trades.fees,
            slippage=result.trades.slippage,
            contributed=result.trades.contributed,
            final_value=final.total if final is not None else None,
        ),
    )


def _ranked(runs: Sequence[CandidateRun]) -> list[CandidateRun]:
    """Highest objective first; a candidate with no objective is absent.

    Absent rather than last: `None` means the figure could not be
    computed, and treating that as the worst possible score would let a
    candidate be beaten by a measurement failure.

    `sorted` is stable, so a dead heat is broken by the grid's order —
    which puts the policy already in production first. A variant never
    displaces the shipped policy by tying with it.
    """
    scored = [run for run in runs if run.outcome.objective is not None]
    return sorted(scored, key=lambda run: -run.outcome.objective)


def _unselected(
    fold: Fold,
    trained: tuple[CandidateRun, ...],
    refusal: str,
    shortlist: tuple[str, ...] = (),
    validated: tuple[CandidateRun, ...] = (),
) -> FoldResult:
    """A fold that ran and could not choose, saying which step stopped it."""
    return FoldResult(
        index=fold.index,
        train=fold.train,
        validation=fold.validation,
        test=fold.test,
        trained=trained,
        shortlist=shortlist,
        validated=validated,
        selected=None,
        tested=None,
        in_sample=None,
        out_of_sample=None,
        degradation=None,
        refusal=refusal,
    )


# -- across folds -----------------------------------------------------


def _stability(folds: Sequence[FoldResult], layout: Partition) -> Stability:
    """What repetition says, or why it cannot say anything yet."""
    selections: dict[str, int] = {}
    for fold in folds:
        if fold.selected is not None:
            selections[fold.selected] = selections.get(fold.selected, 0) + 1

    measured = [fold for fold in folds if fold.out_of_sample is not None]
    values = [fold.out_of_sample for fold in measured]
    degradations = [fold.degradation for fold in folds if fold.degradation is not None]

    refusal = None
    if not folds:
        refusal = layout.refusal
    elif not measured:
        refusal = OBJECTIVE_UNAVAILABLE
    elif len(measured) < 2:
        refusal = SINGLE_FOLD

    if refusal is not None:
        return Stability(
            folds=len(folds),
            measured_folds=len(measured),
            selections=selections,
            most_selected=_most_selected(selections),
            selection_rate=None,
            out_of_sample_mean=None,
            out_of_sample_min=None,
            out_of_sample_max=None,
            out_of_sample_stdev=None,
            degradation_mean=None,
            positive_folds=None,
            refusal=refusal,
        )

    winner = _most_selected(selections)
    return Stability(
        folds=len(folds),
        measured_folds=len(measured),
        selections=selections,
        most_selected=winner,
        selection_rate=(
            Decimal(selections[winner]) / len(measured) if winner else None
        ),
        out_of_sample_mean=sum(values, ZERO) / len(values),
        out_of_sample_min=min(values),
        out_of_sample_max=max(values),
        out_of_sample_stdev=standard_deviation(values),
        degradation_mean=(
            sum(degradations, ZERO) / len(degradations) if degradations else None
        ),
        positive_folds=sum(1 for value in values if value > ZERO),
    )


def _most_selected(selections: dict[str, int]) -> str | None:
    """The candidate that won most folds, ties broken by name.

    By name rather than by insertion order, because a dict built while
    walking folds would make the answer depend on which fold happened to
    be first — and rule 113 wants the same input to give the same result
    however it was assembled.
    """
    if not selections:
        return None
    return min(selections, key=lambda name: (-selections[name], name))


def _empty(
    settings: WalkForwardSettings,
    window: BacktestWindow,
    excluded: tuple[tuple[str, str], ...],
    grid: Sequence[PolicyCandidate],
    refusal: str,
) -> WalkForwardResult:
    """A walk-forward that could not start, saying so rather than zeroing."""
    layout = replace(
        partition(window.start, window.end, settings.scheme),
        folds=(),
        refusal=refusal,
    )
    return WalkForwardResult(
        settings=settings,
        grid_version=WALK_FORWARD_GRID_VERSION,
        window=window,
        universe=(),
        excluded=excluded,
        candidates=tuple(grid),
        partition=layout,
        folds=(),
        stability=Stability(
            folds=0,
            measured_folds=0,
            selections={},
            most_selected=None,
            selection_rate=None,
            out_of_sample_mean=None,
            out_of_sample_min=None,
            out_of_sample_max=None,
            out_of_sample_stdev=None,
            degradation_mean=None,
            positive_folds=None,
            refusal=refusal,
        ),
    )
