"""The backtesting endpoint (AGENTS.md rules 57, 63, 107, 108, 109).

Its own router rather than a branch of `/portfolios`, because a backtest
has no portfolio to read: it *builds* one, from an empty ledger, out of
the tracked universe. What it borrows from the investor is the policy and
the monthly contribution, not the holdings.

`GET` and not `POST` for the reason `/contribution-plan` is: nothing is
stored (rule 16). A backtest is derived, like positions and plans, so
running it twice with the same parameters is the same request twice and
not two resources.
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
from app.domain.backtesting.schemas import (
    BacktestResponse,
    BacktestSettingsResponse,
    BacktestWindowResponse,
    CostModelResponse,
    ExcludedAssetResponse,
    IndexPointResponse,
    TradeStatisticsResponse,
    WealthPointResponse,
)
from app.domain.backtesting.service import (
    STRATEGIES,
    BacktestResult,
    BacktestSettings,
    run_backtest,
)
from app.domain.backtesting.simulation import CostModel
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
    if strategy not in STRATEGIES:
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

    definition = _resolve_benchmark(benchmark) if benchmark else None
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


# -- helpers ---------------------------------------------------------


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
            policy=AllocationPolicyResponse(
                max_asset_weight=result.settings.policy.max_asset_weight,
                max_sector_weight=result.settings.policy.max_sector_weight,
                max_share_per_position=result.settings.policy.max_share_per_position,
                max_positions=result.settings.policy.max_positions,
                min_ticket=result.settings.policy.min_ticket,
                min_coverage=result.settings.policy.min_coverage,
                min_score=result.settings.policy.min_score,
                coverage_tier_width=result.settings.policy.coverage_tier_width,
                rebalance_band=result.settings.policy.rebalance_band,
                require_sector=result.settings.policy.require_sector,
            ),
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
