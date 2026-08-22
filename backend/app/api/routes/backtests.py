"""The backtesting endpoints (AGENTS.md rules 57, 61, 62, 63, 107, 108, 109).

Its own router rather than a branch of `/portfolios`, because a backtest
has no portfolio to read: it *builds* one, from an empty ledger, out of
the tracked universe. What it borrows from the investor is the policy and
the monthly contribution, not the holdings.

`GET` and not `POST` for the reason `/contribution-plan` is: nothing is
stored (rule 16). A backtest is derived, like positions and plans, so
running it twice with the same parameters is the same request twice and
not two resources.

Two routes, and they answer different questions. `GET /backtests` asks
*what would this strategy have done*. `GET /backtests/walk-forward` asks
*would the parameters have held up* — history cut into train, validation
and test, the cut moved forward, and the strategy judged on stability
across repetitions rather than on one better number (rules 61 and 62).
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.data.database import get_db
from app.data.models.assets import Asset
from app.data.models.users import User
from app.domain.backtesting.folds import (
    SEGMENT_MONTHS,
    STEP_MONTHS,
    Segment,
    WalkForwardScheme,
)
from app.domain.backtesting.objectives import SelectionObjective
from app.domain.backtesting.schemas import (
    BacktestResponse,
    BacktestSettingsResponse,
    BacktestWindowResponse,
    CandidateRunResponse,
    CostModelResponse,
    ExcludedAssetResponse,
    FoldResponse,
    IndexPointResponse,
    PolicyCandidateResponse,
    SegmentMetricsResponse,
    SegmentOutcomeResponse,
    SegmentResponse,
    TradeStatisticsResponse,
    WalkForwardPartitionResponse,
    WalkForwardResponse,
    WalkForwardSchemeResponse,
    WalkForwardSettingsResponse,
    WalkForwardStabilityResponse,
    WealthPointResponse,
)
from app.domain.backtesting.service import (
    STRATEGIES,
    BacktestResult,
    BacktestSettings,
    run_backtest,
)
from app.domain.backtesting.simulation import CostModel
from app.domain.backtesting.walkforward import (
    SHORTLIST,
    CandidateRun,
    FoldResult,
    SegmentOutcome,
    WalkForwardResult,
    WalkForwardSettings,
    run_walk_forward,
)
from app.domain.benchmarks.catalog import UnknownBenchmarkError, get_benchmark
from app.domain.benchmarks.schemas import BenchmarkComparisonResponse
from app.domain.recommendations.allocation import DEFAULT_POLICY, AllocationPolicy
from app.domain.recommendations.schemas import AllocationPolicyResponse
from app.domain.recommendations.service import monthly_contribution_of

router = APIRouter(prefix="/backtests", tags=["Backtesting"])


@router.get("", response_model=BacktestResponse)
def run_portfolio_backtest(
    start: date = Query(..., description="First session the simulation may trade on."),
    end: date | None = Query(None, description="Last session. Defaults to today."),
    strategy: str = Query(
        "contribution-plan",
        description=(
            "Which of this project's plans to replay: `contribution-plan` "
            "ranks by score, `rebalance-plan` by distance from target."
        ),
    ),
    amount: Decimal | None = Query(
        None,
        gt=0,
        description=(
            "Monthly contribution. Defaults to the investor profile's, "
            "or R$ 1.000 when no profile exists."
        ),
    ),
    day_of_month: int = Query(
        1,
        ge=1,
        le=31,
        description=(
            "Target day the contribution arrives. It lands on the first "
            "session on or after it, since markets do not open on every "
            "5th."
        ),
    ),
    benchmark: str | None = Query(
        None, description="Benchmark code to measure against, e.g. IBOV or CDI."
    ),
    tickers: list[str] | None = Query(
        None, description="Restrict the universe. Defaults to every active asset."
    ),
    brokerage: Decimal | None = Query(None, ge=0),
    brokerage_rate: Decimal | None = Query(None, ge=0, le=1),
    exchange_rate: Decimal | None = Query(None, ge=0, le=1),
    publication_lag_months: int | None = Query(
        None,
        ge=0,
        le=24,
        description=(
            "Months after a period ends before its statement counts as "
            "public. Defaults to the CVM's three-month DFP deadline; zero "
            "disables the rule and reintroduces look-ahead (rule 109)."
        ),
    ),
    max_asset_weight: Decimal | None = Query(None, gt=0, le=1),
    max_sector_weight: Decimal | None = Query(None, gt=0, le=1),
    max_share_per_position: Decimal | None = Query(None, gt=0, le=1),
    max_positions: int | None = Query(None, ge=1),
    min_ticket: Decimal | None = Query(None, ge=0),
    min_coverage: Decimal | None = Query(None, ge=0, le=1),
    min_score: Decimal | None = Query(None, ge=0, le=100),
    rebalance_band: Decimal | None = Query(None, ge=0, le=1),
    require_sector: bool | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BacktestResponse:
    """Replay one of this project's own plans over history.

    Not *a* strategy — **the** strategy. Both options are the plan an
    endpoint produces today, run month by month over the past with
    everything cut at the date of each decision: prices, the portfolio
    the run itself accumulated, and financial statements filtered by when
    they were **filed** rather than by the period they report (rules 108
    and 109).

    Two answers come back, and neither substitutes for the other.
    `comparison` is time-weighted, so contributions are neutralised and
    the figure is comparable with a benchmark. `wealth` is the money,
    with the contribution line under it — a curve that grew on deposits
    must not be readable as performance (ADR-019).

    ⚠️ **The window may be shorter than the one requested.** A
    total-return series exists only where the price adjustment is
    complete, and a session marked ex with no sized action behind it is a
    distribution this project cannot pay. So the run starts where every
    asset in the universe is measurable, and `window.bounded_by` names
    the asset that decided it. Assets that cannot be replayed at all come
    back in `excluded`, by name and reason, rather than being dropped.

    ⚠️ **Costs are modelled and slippage is measured** (rule 107). Fees
    default to B3's own rate with no brokerage, which is a choice and is
    echoed back in `settings.costs`. Slippage is not assumed at a rate:
    an order decided on one session fills on the next, and the gap
    between those two prices is summed from what actually happened.

    Every figure defined on closed trades comes back `null`, because
    nothing this project ships ever sells (ADR-028). That is the honest
    answer; `trades.closed_trades` at zero is what says so.

    Nothing is stored (rule 16), and nothing is fetched: the run reads
    stored prices, statements and corporate actions only (rule 23), which
    must have been synced first.
    """
    _ensure_strategy(strategy)
    last = _closing_date(start, end)
    definition = _resolve_benchmark(benchmark) if benchmark else None
    universe = _required_universe(db, tickers)

    settings = BacktestSettings(
        start=start,
        end=last,
        strategy=strategy,
        contribution=(
            amount
            if amount is not None
            else monthly_contribution_of(db, current_user.id)
        ),
        day_of_month=day_of_month,
        costs=_costs_with(
            brokerage=brokerage,
            brokerage_rate=brokerage_rate,
            exchange_rate=exchange_rate,
        ),
        policy=_policy_with(
            max_asset_weight=max_asset_weight,
            max_sector_weight=max_sector_weight,
            max_share_per_position=max_share_per_position,
            max_positions=max_positions,
            min_ticket=min_ticket,
            min_coverage=min_coverage,
            min_score=min_score,
            rebalance_band=rebalance_band,
            require_sector=require_sector,
        ),
        **(
            {"publication_lag_months": publication_lag_months}
            if publication_lag_months is not None
            else {}
        ),
    )

    return _response(run_backtest(db, universe, settings, definition))


@router.get("/walk-forward", response_model=WalkForwardResponse)
def run_strategy_walk_forward(
    start: date = Query(..., description="Earliest session the folds may cover."),
    end: date | None = Query(None, description="Last session. Defaults to today."),
    strategy: str = Query("contribution-plan"),
    amount: Decimal | None = Query(None, gt=0),
    day_of_month: int = Query(1, ge=1, le=31),
    tickers: list[str] | None = Query(
        None, description="Restrict the universe. Defaults to every active asset."
    ),
    segment_months: int = Query(
        SEGMENT_MONTHS,
        ge=1,
        le=120,
        description=(
            "Length of each of train, validation and test. All three are "
            "the same length on purpose: a shorter test segment measures a "
            "younger portfolio, not a worse strategy."
        ),
    ),
    step_months: int = Query(
        STEP_MONTHS,
        ge=1,
        le=120,
        description=(
            "How far the whole fold slides between repetitions. Equal to "
            "the segment by default, which tiles the test segments without "
            "overlapping them."
        ),
    ),
    objective: SelectionObjective = Query(
        SelectionObjective.SHARPE,
        description=(
            "The single figure each fold ranks candidates by. `sharpe` "
            "needs a CDI series covering the segment and is unrankable "
            "without one; `total-return` needs nothing beyond the run."
        ),
    ),
    shortlist: int = Query(
        SHORTLIST,
        ge=1,
        le=20,
        description="How many trained candidates go forward to validation.",
    ),
    brokerage: Decimal | None = Query(None, ge=0),
    brokerage_rate: Decimal | None = Query(None, ge=0, le=1),
    exchange_rate: Decimal | None = Query(None, ge=0, le=1),
    publication_lag_months: int | None = Query(None, ge=0, le=24),
    max_asset_weight: Decimal | None = Query(None, gt=0, le=1),
    max_sector_weight: Decimal | None = Query(None, gt=0, le=1),
    max_share_per_position: Decimal | None = Query(None, gt=0, le=1),
    max_positions: int | None = Query(None, ge=1),
    min_ticket: Decimal | None = Query(None, ge=0),
    min_coverage: Decimal | None = Query(None, ge=0, le=1),
    min_score: Decimal | None = Query(None, ge=0, le=100),
    rebalance_band: Decimal | None = Query(None, ge=0, le=1),
    require_sector: bool | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WalkForwardResponse:
    """Validate the strategy's parameters out-of-sample (rules 61 and 62).

    The replayable history is cut into `Train → Validate → Test`, and the
    cut moves forward. Every candidate is measured on train, the shortlist
    is re-measured on validation, and the winner — and only the winner —
    is run on test. **Nothing measured on test ever reaches a selection**,
    which is the single property that makes an out-of-sample figure worth
    reading.

    The candidates are a declared grid, not a sweep: each differs from the
    policy you passed in exactly one field, and each carries the question
    it answers. Rule 60 is about not tuning until the past looks good, and
    a cross product of the same axes would be that with a walk-forward
    wrapped around it.

    ⚠️ **The figure that answers the question is
    `stability.degradation_mean`.** A strategy whose out-of-sample results
    track its in-sample ones has parameters that describe something; one
    whose results collapse has parameters that described the sample they
    were chosen on. `stability.selection_rate` is the other half: a
    walk-forward that picks a different winner every fold has found noise.

    ⚠️ **Every segment starts from an empty portfolio.** That is what
    makes candidates comparable to each other and in-sample comparable to
    out-of-sample, and it means each segment measures the strategy
    *accumulating* rather than running on a mature portfolio.

    ⚠️ **This runs many backtests** — one per candidate on train, one per
    shortlisted candidate on validation, and one on test, for every fold.
    Nothing is fetched and nothing is stored (rules 16 and 23), but the
    replay is real work.

    `partition.refusal` at `WINDOW_TOO_SHORT` means the replayable window
    could not hold three segments, with `required_months` and
    `available_months` saying by how much. The fix is upstream — ingest
    the corporate actions that truncate the total-return series (ADR-032)
    — and never shortening the segments until they fit.
    """
    _ensure_strategy(strategy)
    last = _closing_date(start, end)
    universe = _required_universe(db, tickers)

    settings = WalkForwardSettings(
        start=start,
        end=last,
        strategy=strategy,
        contribution=(
            amount
            if amount is not None
            else monthly_contribution_of(db, current_user.id)
        ),
        day_of_month=day_of_month,
        costs=_costs_with(
            brokerage=brokerage,
            brokerage_rate=brokerage_rate,
            exchange_rate=exchange_rate,
        ),
        policy=_policy_with(
            max_asset_weight=max_asset_weight,
            max_sector_weight=max_sector_weight,
            max_share_per_position=max_share_per_position,
            max_positions=max_positions,
            min_ticket=min_ticket,
            min_coverage=min_coverage,
            min_score=min_score,
            rebalance_band=rebalance_band,
            require_sector=require_sector,
        ),
        scheme=WalkForwardScheme(
            segment_months=segment_months, step_months=step_months
        ),
        objective=objective,
        shortlist=shortlist,
        **(
            {"publication_lag_months": publication_lag_months}
            if publication_lag_months is not None
            else {}
        ),
    )

    return _walk_forward_response(run_walk_forward(db, universe, settings))


# -- helpers ---------------------------------------------------------


def _ensure_strategy(strategy: str) -> None:
    """Reject a strategy this project does not actually run."""
    if strategy in STRATEGIES:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": {
                "code": "UNKNOWN_STRATEGY",
                "message": (
                    f"Unknown strategy {strategy}. Available: "
                    f"{', '.join(sorted(STRATEGIES))}."
                ),
            }
        },
    )


def _closing_date(start: date, end: date | None) -> date:
    """`end`, or today, having checked it does not precede `start`."""
    last = end or datetime.now(UTC).date()
    if last < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_WINDOW",
                    "message": "The end of the window precedes its start.",
                }
            },
        )
    return last


def _required_universe(db: Session, tickers: list[str] | None) -> list[Asset]:
    """The universe, or a 404 saying there is nothing to replay."""
    universe = _universe(db, tickers)
    if not universe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "EMPTY_UNIVERSE",
                    "message": (
                        "No active asset matches this request. Track one, or "
                        "widen the ticker filter."
                    ),
                }
            },
        )
    return universe


def _universe(db: Session, tickers: list[str] | None) -> list[Asset]:
    """Every active asset, or the subset asked for.

    Ordered by ticker so a run's universe — and therefore every tie the
    allocator breaks by ticker — does not depend on insertion order
    (rule 113).
    """
    query = db.query(Asset).filter(Asset.is_active.is_(True))
    if tickers:
        query = query.filter(Asset.ticker.in_([t.upper() for t in tickers]))
    return list(query.order_by(Asset.ticker))


def _resolve_benchmark(code: str):
    """The catalog entry for `code`, or a 404 naming it."""
    try:
        return get_benchmark(code)
    except UnknownBenchmarkError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "BENCHMARK_NOT_FOUND",
                    "message": f"Unknown benchmark {code}.",
                }
            },
        ) from exc


def _policy_with(**overrides: object) -> AllocationPolicy:
    """The default policy with whatever the request actually set.

    `None` means "not sent" rather than "no limit", so dropping the unset
    ones keeps an omitted parameter at its conservative default instead
    of clearing it (rule 32).
    """
    given = {name: value for name, value in overrides.items() if value is not None}
    return replace(DEFAULT_POLICY, **given) if given else DEFAULT_POLICY


def _policy_response(policy: AllocationPolicy) -> AllocationPolicyResponse:
    """The limits a result was computed under, as the API reports them.

    One place rather than one per route: the walk-forward echoes a policy
    per candidate, and a second transcription is a chance for the two
    endpoints to describe the same dataclass differently.
    """
    return AllocationPolicyResponse(
        max_asset_weight=policy.max_asset_weight,
        max_sector_weight=policy.max_sector_weight,
        max_share_per_position=policy.max_share_per_position,
        max_positions=policy.max_positions,
        min_ticket=policy.min_ticket,
        min_coverage=policy.min_coverage,
        min_score=policy.min_score,
        coverage_tier_width=policy.coverage_tier_width,
        rebalance_band=policy.rebalance_band,
        require_sector=policy.require_sector,
    )


def _costs_with(**overrides: object) -> CostModel:
    """The default cost model with whatever the request actually set.

    Note what an omitted `exchange_rate` means here: B3's own fee still
    applies. Rule 107 says a backtest without costs is not a final
    result, so zero has to be asked for explicitly.
    """
    given = {name: value for name, value in overrides.items() if value is not None}
    return replace(CostModel(), **given) if given else CostModel()


def _response(result: BacktestResult) -> BacktestResponse:
    """The run as the API reports it."""
    return BacktestResponse(
        settings=BacktestSettingsResponse(
            start=result.settings.start,
            end=result.settings.end,
            strategy=result.settings.strategy,
            contribution=result.settings.contribution,
            day_of_month=result.settings.day_of_month,
            publication_lag_months=result.settings.publication_lag_months,
            costs=CostModelResponse(
                brokerage=result.settings.costs.brokerage,
                brokerage_rate=result.settings.costs.brokerage_rate,
                exchange_rate=result.settings.costs.exchange_rate,
            ),
            policy=_policy_response(result.settings.policy),
        ),
        window=BacktestWindowResponse(
            requested_start=result.window.requested_start,
            requested_end=result.window.requested_end,
            start=result.window.start,
            end=result.window.end,
            bounded_by=result.window.bounded_by,
        ),
        universe=list(result.universe),
        excluded=[
            ExcludedAssetResponse(ticker=ticker, reason=reason)
            for ticker, reason in result.excluded
        ],
        comparison=(
            BenchmarkComparisonResponse.model_validate(result.comparison)
            if result.comparison is not None
            else None
        ),
        alpha=result.alpha,
        index=[
            IndexPointResponse(date=point.date, value=point.adjusted_close)
            for point in result.index
        ],
        wealth=[
            WealthPointResponse(
                date=point.date,
                holdings=point.holdings,
                cash=point.cash,
                total=point.total,
                contributed=point.contributed,
            )
            for point in result.wealth
        ],
        trades=TradeStatisticsResponse(
            trades=result.trades.trades,
            buys=result.trades.buys,
            sells=result.trades.sells,
            closed_trades=result.trades.closed_trades,
            wins=result.trades.wins,
            losses=result.trades.losses,
            win_rate=result.trades.win_rate,
            average_win=result.trades.average_win,
            average_loss=result.trades.average_loss,
            profit_factor=result.trades.profit_factor,
            expectancy=result.trades.expectancy,
            realized_result=result.trades.realized_result,
            fees=result.trades.fees,
            slippage=result.trades.slippage,
            slippage_paid=result.trades.slippage_paid,
            slippage_earned=result.trades.slippage_earned,
            dividends_received=result.trades.dividends_received,
            contributed=result.trades.contributed,
            unfilled=result.trades.unfilled,
        ),
        sources=list(result.sources),
    )


def _walk_forward_response(result: WalkForwardResult) -> WalkForwardResponse:
    """The walk-forward as the API reports it."""
    return WalkForwardResponse(
        settings=WalkForwardSettingsResponse(
            start=result.settings.start,
            end=result.settings.end,
            strategy=result.settings.strategy,
            contribution=result.settings.contribution,
            day_of_month=result.settings.day_of_month,
            publication_lag_months=result.settings.publication_lag_months,
            costs=CostModelResponse(
                brokerage=result.settings.costs.brokerage,
                brokerage_rate=result.settings.costs.brokerage_rate,
                exchange_rate=result.settings.costs.exchange_rate,
            ),
            policy=_policy_response(result.settings.policy),
            scheme=WalkForwardSchemeResponse(
                segment_months=result.settings.scheme.segment_months,
                step_months=result.settings.scheme.step_months,
            ),
            objective=result.settings.objective.value,
            shortlist=result.settings.shortlist,
        ),
        grid_version=result.grid_version,
        window=BacktestWindowResponse(
            requested_start=result.window.requested_start,
            requested_end=result.window.requested_end,
            start=result.window.start,
            end=result.window.end,
            bounded_by=result.window.bounded_by,
        ),
        universe=list(result.universe),
        excluded=[
            ExcludedAssetResponse(ticker=ticker, reason=reason)
            for ticker, reason in result.excluded
        ],
        candidates=[
            PolicyCandidateResponse(
                name=candidate.name,
                question=candidate.question,
                policy=_policy_response(candidate.policy),
            )
            for candidate in result.candidates
        ],
        partition=WalkForwardPartitionResponse(
            folds=len(result.partition.folds),
            required_months=result.partition.required_months,
            available_months=result.partition.available_months,
            refusal=result.partition.refusal,
        ),
        folds=[_fold_response(fold) for fold in result.folds],
        stability=WalkForwardStabilityResponse(
            folds=result.stability.folds,
            measured_folds=result.stability.measured_folds,
            selections=dict(result.stability.selections),
            most_selected=result.stability.most_selected,
            selection_rate=result.stability.selection_rate,
            out_of_sample_mean=result.stability.out_of_sample_mean,
            out_of_sample_min=result.stability.out_of_sample_min,
            out_of_sample_max=result.stability.out_of_sample_max,
            out_of_sample_stdev=result.stability.out_of_sample_stdev,
            degradation_mean=result.stability.degradation_mean,
            positive_folds=result.stability.positive_folds,
            refusal=result.stability.refusal,
        ),
    )


def _fold_response(fold: FoldResult) -> FoldResponse:
    """One `Train → Validate → Test`, and what survived it."""
    return FoldResponse(
        index=fold.index,
        train=_segment_response(fold.train),
        validation=_segment_response(fold.validation),
        test=_segment_response(fold.test),
        trained=[_candidate_run_response(run) for run in fold.trained],
        shortlist=list(fold.shortlist),
        validated=[_candidate_run_response(run) for run in fold.validated],
        selected=fold.selected,
        tested=(_outcome_response(fold.tested) if fold.tested is not None else None),
        in_sample=fold.in_sample,
        out_of_sample=fold.out_of_sample,
        degradation=fold.degradation,
        refusal=fold.refusal,
    )


def _segment_response(segment: Segment) -> SegmentResponse:
    return SegmentResponse(start=segment.start, end=segment.end)


def _candidate_run_response(run: CandidateRun) -> CandidateRunResponse:
    """One candidate over one segment, joined to `candidates` by name."""
    return CandidateRunResponse(name=run.name, outcome=_outcome_response(run.outcome))


def _outcome_response(outcome: SegmentOutcome) -> SegmentOutcomeResponse:
    return SegmentOutcomeResponse(
        metrics=SegmentMetricsResponse(
            observations=outcome.metrics.observations,
            total_return=outcome.metrics.total_return,
            cagr=outcome.metrics.cagr,
            volatility=outcome.metrics.volatility,
            max_drawdown=outcome.metrics.max_drawdown,
            sharpe=outcome.metrics.sharpe,
            sortino=outcome.metrics.sortino,
        ),
        objective=outcome.objective,
        trades=outcome.trades,
        fees=outcome.fees,
        slippage=outcome.slippage,
        contributed=outcome.contributed,
        final_value=outcome.final_value,
    )
