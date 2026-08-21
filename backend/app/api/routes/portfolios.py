from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_ai_provider, get_current_user
from app.core.config import settings
from app.data.database import get_db
from app.data.models.assets import Asset
from app.data.models.portfolio import Portfolio, Transaction, TransactionTypeEnum
from app.data.models.users import User
from app.domain.ai.facts import (
    asset_score_facts,
    contribution_plan_facts,
    portfolio_performance_facts,
)
from app.domain.ai.schemas import Explanation, FactPack
from app.domain.ai.service import explain as explain_facts
from app.domain.benchmarks.catalog import UnknownBenchmarkError, get_benchmark
from app.domain.benchmarks.schemas import (
    BenchmarkComparisonResponse,
    SeriesPerformanceResponse,
)
from app.domain.benchmarks.service import (
    compare_portfolio_with_benchmark,
    portfolio_series,
)
from app.domain.market_data.service import latest_closes
from app.domain.portfolio.schemas import (
    AssetPositionResponse,
    IndexPointResponse,
    PortfolioCreate,
    PortfolioPositionsResponse,
    PortfolioResponse,
    PortfolioSeriesResponse,
    PortfolioUpdate,
    TransactionCreate,
    TransactionResponse,
    WealthPointResponse,
)
from app.domain.portfolio.service import (
    ZERO,
    compute_asset_quantity,
    compute_net_contributions,
    compute_positions,
)
from app.domain.portfolio.valuation import value_positions
from app.domain.recommendations.allocation import (
    DEFAULT_POLICY,
    AllocationPlan,
    AllocationPolicy,
)
from app.domain.recommendations.schemas import (
    AllocationPolicyResponse,
    AllocationResponse,
    AssetScoreResponse,
    AssetTargetResponse,
    ContributionPlanResponse,
    PortfolioScoresResponse,
    PortfolioTargetsResponse,
    RebalanceAllocationResponse,
    RebalancePlanResponse,
    RebalanceSkippedResponse,
    SkippedCandidateResponse,
    SubScoreResponse,
)
from app.domain.recommendations.scoring import SCORING_FORMULA_VERSION, AssetScore
from app.domain.recommendations.service import (
    plan_contribution,
    plan_rebalance,
    portfolio_targets,
    score_universe,
)
from app.integrations.ai.base import AIProvider
from app.integrations.ai.exceptions import (
    AINotConfiguredError,
    AIResponseBlockedError,
    AIUnavailableError,
    InvalidAIResponseError,
)

router = APIRouter(prefix="/portfolios", tags=["Portfolio"])


def _get_owned_portfolio(db: Session, portfolio_id: int, user: User) -> Portfolio:
    """Fetch a portfolio, scoped to its owner.

    Returns 404 (not 403) when the portfolio exists but belongs to another
    user, so a caller cannot use the response to probe which portfolio IDs
    exist for other accounts.
    """
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
        .first()
    )
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "PORTFOLIO_NOT_FOUND",
                    "message": "Portfolio was not found.",
                }
            },
        )
    return portfolio


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    payload: PortfolioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Portfolio:
    portfolio = Portfolio(user_id=current_user.id, name=payload.name)
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


@router.get("", response_model=list[PortfolioResponse])
def list_portfolios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Portfolio]:
    return (
        db.query(Portfolio)
        .filter(Portfolio.user_id == current_user.id)
        .order_by(Portfolio.created_at)
        .all()
    )


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Portfolio:
    return _get_owned_portfolio(db, portfolio_id, current_user)


@router.patch("/{portfolio_id}", response_model=PortfolioResponse)
def update_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Portfolio:
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    portfolio.name = payload.name
    db.commit()
    db.refresh(portfolio)
    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    db.delete(portfolio)
    db.commit()


@router.post(
    "/{portfolio_id}/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    portfolio_id: int,
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    """Record a BUY, SELL, DIVIDEND, DEPOSIT or WITHDRAWAL transaction.

    Positions are derived from the transaction ledger (AGENTS.md rule 16),
    never stored independently, so this endpoint only appends to that
    ledger. The one invariant it does enforce is that a SELL can never
    exceed the currently held quantity for that asset.
    """
    _get_owned_portfolio(db, portfolio_id, current_user)

    if payload.asset_id is not None:
        asset = db.get(Asset, payload.asset_id)
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "ASSET_NOT_FOUND",
                        "message": "Asset was not found.",
                    }
                },
            )

    if payload.type == TransactionTypeEnum.SELL:
        existing_transactions = (
            db.query(Transaction)
            .filter(
                Transaction.portfolio_id == portfolio_id,
                Transaction.asset_id == payload.asset_id,
            )
            .all()
        )
        held_quantity = compute_asset_quantity(existing_transactions, payload.asset_id)
        if payload.quantity > held_quantity:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "error": {
                        "code": "INSUFFICIENT_POSITION",
                        "message": (
                            f"Cannot sell {payload.quantity} units: "
                            f"only {held_quantity} currently held."
                        ),
                    }
                },
            )

    transaction = Transaction(
        portfolio_id=portfolio_id,
        asset_id=payload.asset_id,
        type=payload.type,
        quantity=payload.quantity,
        price=payload.price,
        fees=payload.fees,
        transaction_date=payload.transaction_date,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.get("/{portfolio_id}/transactions", response_model=list[TransactionResponse])
def list_transactions(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Transaction]:
    _get_owned_portfolio(db, portfolio_id, current_user)
    return (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == portfolio_id)
        .order_by(Transaction.transaction_date, Transaction.id)
        .all()
    )


@router.get("/{portfolio_id}/positions", response_model=PortfolioPositionsResponse)
def get_portfolio_positions(
    portfolio_id: int,
    as_of: date | None = Query(
        None,
        description=(
            "Value the positions with the last close on or before this "
            "date. Defaults to the latest stored price."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioPositionsResponse:
    """Consolidated positions, at cost and at market.

    Quantities, average price and realised P&L are derived entirely from
    the transaction ledger (rule 16). Market value is `quantity × close`,
    computed here rather than in the frontend, which presents and does
    not calculate (rule 73).

    ⚠️ **Read `unvalued_positions` before reading `valued_market_value`.**
    An asset with no stored price makes its own line absent, not the
    whole total — so the total can cover part of the portfolio, and its
    name says so. `unvalued_invested` measures what it leaves out.

    `as_of` truncates the **ledger** as well as the prices, so it reports
    the portfolio as it stood on that date rather than today's holdings
    priced backwards.

    ⚠️ Quantities are replayed from the ledger alone, which records what
    was traded and knows nothing of splits or groupings. A position held
    through a corporate action that changed the share count reads at the
    old count until the investor records the change — visible here for
    the first time, because cost basis never depended on it.

    Reads only stored data (rule 23): opening this never calls the price
    provider, so an asset nobody synced is simply unvalued.
    """
    _get_owned_portfolio(db, portfolio_id, current_user)

    query = db.query(Transaction).filter(Transaction.portfolio_id == portfolio_id)
    if as_of is not None:
        # The ledger is truncated too, not only the prices. Valuing
        # today's holdings at a past close answers a question nobody
        # asked -- what the portfolio you have now would have been worth
        # then -- and reads as history. `as_of` means the portfolio as it
        # stood, at the prices that stood with it (rule 108).
        query = query.filter(
            Transaction.transaction_date
            < datetime.combine(as_of, time.min) + timedelta(days=1)
        )
    transactions = query.all()
    positions = compute_positions(transactions)

    tickers: dict[int, str] = {}
    if positions:
        assets = db.query(Asset).filter(Asset.id.in_(positions.keys())).all()
        tickers = {asset.id: asset.ticker for asset in assets}

    valuation = value_positions(positions, latest_closes(db, positions, as_of))

    position_items = [
        AssetPositionResponse(
            asset_id=valued.asset_id,
            ticker=tickers.get(valued.asset_id, "UNKNOWN"),
            quantity=valued.quantity,
            average_price=positions[valued.asset_id].average_price,
            invested_amount=valued.invested_amount,
            realized_pnl=positions[valued.asset_id].realized_pnl,
            dividends_received=positions[valued.asset_id].dividends_received,
            last_price=valued.last_price,
            price_date=valued.price_date,
            market_value=valued.market_value,
            unrealised_pnl=valued.unrealised_pnl,
        )
        for valued in valuation.positions
    ]

    return PortfolioPositionsResponse(
        portfolio_id=portfolio_id,
        positions=position_items,
        valued_market_value=valuation.valued_market_value,
        valued_invested=valuation.valued_invested,
        unrealised_pnl=valuation.unrealised_pnl,
        unvalued_positions=valuation.unvalued_positions,
        unvalued_invested=valuation.unvalued_invested,
        oldest_price_date=valuation.oldest_price_date,
        newest_price_date=valuation.newest_price_date,
        total_invested=sum((p.invested_amount for p in positions.values()), ZERO),
        total_realized_pnl=sum((p.realized_pnl for p in positions.values()), ZERO),
        total_dividends_received=sum(
            (p.dividends_received for p in positions.values()), ZERO
        ),
        net_contributions=compute_net_contributions(transactions),
    )


@router.get(
    "/{portfolio_id}/benchmarks/{code}",
    response_model=BenchmarkComparisonResponse,
)
def compare_portfolio_against_benchmark(
    portfolio_id: int,
    code: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BenchmarkComparisonResponse:
    """Compare this portfolio's performance against a benchmark.

    The portfolio side is a **time-weighted** index, so contributions and
    withdrawals do not count as performance (AGENTS.md rule 26) — without
    that, a portfolio receiving a monthly contribution would appear to
    beat every benchmark in a year the investor lost money.

    Reads only stored data (rule 23). Both the prices and the benchmark
    series must have been synced first, and each side reports the window
    it could actually measure.
    """
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    definition = _resolve_benchmark(code)
    comparison = compare_portfolio_with_benchmark(db, portfolio, definition, start, end)
    return BenchmarkComparisonResponse.model_validate(comparison)


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


@router.get("/{portfolio_id}/series", response_model=PortfolioSeriesResponse)
def get_portfolio_series(
    portfolio_id: int,
    benchmark: str | None = Query(
        None,
        description=(
            "Benchmark code to draw alongside the index — CDI, IBOV, "
            "IPCA or SELIC. Omitted, only the portfolio's own series "
            "come back."
        ),
    ),
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioSeriesResponse:
    """The two curves an evolution chart draws (roadmap §23, rule 74).

    `wealth` is patrimônio in BRL — raw closes, contributions included —
    with `invested` beside it so the part that is the investor's own
    money is visible rather than read as performance.

    `index` is the time-weighted level, which neutralises contributions
    and is the only one comparable with a benchmark (ADR-019). When a
    benchmark is asked for, both are clipped to the window they share and
    rebased at `base_date`, so neither line starts with a head start the
    reader cannot see.

    Reads only stored data (rule 23); prices and benchmark values must
    have been synced first. A date where any held asset has no stored
    price is absent from both series rather than being valued partially.
    """
    owned = _get_owned_portfolio(db, portfolio_id, current_user)

    definition = None
    if benchmark is not None:
        try:
            definition = get_benchmark(benchmark)
        except UnknownBenchmarkError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "BENCHMARK_NOT_FOUND",
                        "message": f"Unknown benchmark {benchmark}.",
                    }
                },
            ) from exc

    series = portfolio_series(db, owned, definition, start, end)

    return PortfolioSeriesResponse(
        portfolio_id=owned.id,
        currency="BRL",
        base=series.aligned.base,
        base_date=series.aligned.base_date,
        end_date=series.aligned.end_date,
        sources=list(series.sources),
        generated_at=datetime.now(UTC),
        wealth=[
            WealthPointResponse(
                date=point.date, value=point.value, invested=point.invested
            )
            for point in series.value
        ],
        index=[
            IndexPointResponse(date=point.date, value=point.adjusted_close)
            for point in series.aligned.subject
        ],
        benchmark_code=definition.code if definition else None,
        benchmark_name=definition.name if definition else None,
        benchmark_index=[
            IndexPointResponse(date=point.date, value=point.adjusted_close)
            for point in series.aligned.benchmark
        ],
        subject=SeriesPerformanceResponse.model_validate(series.subject),
        benchmark=(
            SeriesPerformanceResponse.model_validate(series.benchmark)
            if series.benchmark is not None
            else None
        ),
    )


@router.get("/{portfolio_id}/scores", response_model=PortfolioScoresResponse)
def get_portfolio_scores(
    portfolio_id: int,
    start: date | None = None,
    as_of: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioScoresResponse:
    """Score every tracked asset against this portfolio.

    Scores are **relative to the portfolio** (AGENTS.md rule 31): the
    Diversification pillar reads its current concentration, so the same
    asset scores differently for an investor who already holds 15% of it.

    Read `coverage` before comparing two scores. With the fundamentals
    source unavailable, most assets are scored on Risk and
    Diversification alone, and a score resting on 40% of the formula is
    not comparable with one resting on all of it.

    Reads only stored data (rule 23); prices, benchmarks and indicators
    must have been synced first.
    """
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    scored = score_universe(db, portfolio, start=start, as_of=as_of)

    return PortfolioScoresResponse(
        portfolio_id=portfolio.id,
        formula_version=SCORING_FORMULA_VERSION,
        scores=[_asset_score_response(asset, score) for asset, score in scored],
    )


@router.get(
    "/{portfolio_id}/contribution-plan", response_model=ContributionPlanResponse
)
def get_contribution_plan(
    portfolio_id: int,
    amount: Decimal | None = Query(
        None,
        gt=0,
        description=(
            "How much to allocate. Defaults to the investor profile's "
            "monthly contribution, or R$ 1.000 when no profile exists."
        ),
    ),
    max_asset_weight: Decimal | None = Query(None, gt=0, le=1),
    max_sector_weight: Decimal | None = Query(None, gt=0, le=1),
    max_share_per_position: Decimal | None = Query(None, gt=0, le=1),
    max_positions: int | None = Query(None, ge=1),
    min_ticket: Decimal | None = Query(None, ge=0),
    min_coverage: Decimal | None = Query(None, ge=0, le=1),
    min_score: Decimal | None = Query(None, ge=0, le=100),
    require_sector: bool | None = Query(None),
    start: date | None = None,
    as_of: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContributionPlanResponse:
    """Where the next contribution goes, and why (rules 31/32/33).

    Answers *"dado meu patrimônio atual e R$ 1.000 de novo aporte, onde
    esse dinheiro melhora a carteira?"* — not "which asset scores
    highest". The scores are already relative to this portfolio, and the
    plan then respects the concentration limits on top.

    Every limit is overridable per request, because rule 32 requires the
    weights to be configurable and does not assume two conservative
    investors hold the same thing. Omitted parameters keep the default
    conservative policy, which is echoed back in `policy`.

    Nothing is stored: a plan is derived from the ledger, the scores and
    the policy, exactly as positions are (rule 16).

    Reads only stored data (rule 23); prices, benchmarks and indicators
    must have been synced first.
    """
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)

    policy = _policy_with(
        max_asset_weight=max_asset_weight,
        max_sector_weight=max_sector_weight,
        max_share_per_position=max_share_per_position,
        max_positions=max_positions,
        min_ticket=min_ticket,
        min_coverage=min_coverage,
        min_score=min_score,
        require_sector=require_sector,
    )

    plan = plan_contribution(
        db,
        portfolio,
        contribution=amount,
        start=start,
        as_of=as_of,
        policy=policy,
    )
    return _contribution_plan_response(portfolio.id, plan)


def _contribution_plan_response(
    portfolio_id: int, plan: AllocationPlan
) -> ContributionPlanResponse:
    """The plan as the API reports it.

    Extracted so the explanation endpoint can build the *same* object the
    plain endpoint returns. An explanation that described a
    separately-assembled response would be explaining something the
    investor is not looking at, and the difference would be invisible.
    """
    return ContributionPlanResponse(
        portfolio_id=portfolio_id,
        rules_version=plan.rules_version,
        formula_version=plan.formula_version,
        policy=_policy_response(plan.policy),
        contribution=plan.contribution,
        allocated=plan.allocated,
        unallocated=plan.unallocated,
        base_value=plan.base_value,
        allocations=[
            AllocationResponse(
                ticker=item.ticker,
                asset_id=item.asset_id,
                name=item.name,
                sector=item.sector,
                amount=item.amount,
                rank=item.rank,
                final_score=item.final_score,
                coverage=item.coverage,
                coverage_tier=item.coverage_tier,
                headroom=item.headroom,
                limited_by=item.limited_by.value,
                weight_before=item.weight_before,
                weight_after=item.weight_after,
                sub_scores=[
                    SubScoreResponse.model_validate(sub)
                    for sub in item.score.sub_scores
                ],
            )
            for item in plan.allocations
        ],
        skipped=[
            SkippedCandidateResponse(
                ticker=item.ticker,
                asset_id=item.asset_id,
                name=item.name,
                reason=item.reason.value,
                detail=item.detail,
                final_score=item.final_score,
                coverage=item.coverage,
            )
            for item in plan.skipped
        ],
    )


@router.get("/{portfolio_id}/rebalance", response_model=PortfolioTargetsResponse)
def get_portfolio_rebalance(
    portfolio_id: int,
    max_asset_weight: Decimal | None = Query(None, gt=0, le=1),
    max_sector_weight: Decimal | None = Query(None, gt=0, le=1),
    min_coverage: Decimal | None = Query(None, ge=0, le=1),
    min_score: Decimal | None = Query(None, ge=0, le=100),
    rebalance_band: Decimal | None = Query(
        None,
        ge=0,
        le=1,
        description=(
            "How far from its target a weight may sit before it counts as "
            "off-target. Defaults to 0.02, or 2 percentage points."
        ),
    ),
    require_sector: bool | None = Query(None),
    start: date | None = None,
    as_of: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioTargetsResponse:
    """Current weight, target weight and gap for every asset (rule 34).

    Answers *"how far is my portfolio from where it should be, and in
    which names?"*. Rows come back most underweight first, which is the
    priority order rule 34 asks for.

    ⚠️ **The target is built from merit, not from the score the
    contribution plan ranks by.** Merit drops the Diversification pillar,
    because that pillar reads the very portfolio being targeted: a target
    proportional to `final_score` recedes as the portfolio approaches it,
    and the gap would not be a distance to anything (ADR-027).
    Concentration is still enforced, as the ceilings that trim the
    targets — the same ones the plan respects.

    Read `unassigned` alongside the rows. With few rateable assets the
    ceilings cannot hand out the whole portfolio, and the remainder is
    reported rather than pushed onto whichever names happened to be
    scorable.

    A target of zero on something the investor holds is not a sell
    instruction. Nothing here sells; a portfolio taking monthly
    contributions closes that gap by dilution.

    Nothing is stored: the table is derived from the ledger, the scores
    and the policy, exactly as positions are (rule 16).

    Reads only stored data (rule 23); prices, benchmarks and indicators
    must have been synced first.
    """
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)

    policy = _policy_with(
        max_asset_weight=max_asset_weight,
        max_sector_weight=max_sector_weight,
        min_coverage=min_coverage,
        min_score=min_score,
        rebalance_band=rebalance_band,
        require_sector=require_sector,
    )

    targets = portfolio_targets(db, portfolio, start=start, as_of=as_of, policy=policy)

    return PortfolioTargetsResponse(
        portfolio_id=portfolio.id,
        model_version=targets.model_version,
        formula_version=targets.formula_version,
        policy=_policy_response(targets.policy),
        invested=targets.invested,
        assigned=targets.assigned,
        unassigned=targets.unassigned,
        underweight_gap=targets.underweight_gap,
        overweight_gap=targets.overweight_gap,
        untracked_weight=targets.untracked_weight,
        targets=[
            AssetTargetResponse(
                ticker=row.ticker,
                asset_id=row.asset_id,
                name=row.name,
                sector=row.sector,
                merit_score=row.merit_score,
                merit_coverage=row.merit_coverage,
                current_weight=row.current_weight,
                target_weight=row.target_weight,
                weight_gap=row.weight_gap,
                status=row.status.value,
                limited_by=row.limited_by.value if row.limited_by else None,
                excluded=row.excluded.value if row.excluded else None,
                detail=row.detail,
                final_score=row.score.final_score,
                coverage=row.score.coverage,
                sub_scores=[
                    SubScoreResponse.model_validate(sub) for sub in row.score.sub_scores
                ],
            )
            for row in targets.targets
        ],
    )


@router.get("/{portfolio_id}/rebalance-plan", response_model=RebalancePlanResponse)
def get_rebalance_plan(
    portfolio_id: int,
    amount: Decimal | None = Query(
        None,
        gt=0,
        description=(
            "How much to allocate. Defaults to the investor profile's "
            "monthly contribution, or R$ 1.000 when no profile exists."
        ),
    ),
    max_asset_weight: Decimal | None = Query(None, gt=0, le=1),
    max_sector_weight: Decimal | None = Query(None, gt=0, le=1),
    max_positions: int | None = Query(None, ge=1),
    min_ticket: Decimal | None = Query(None, ge=0),
    min_coverage: Decimal | None = Query(None, ge=0, le=1),
    min_score: Decimal | None = Query(None, ge=0, le=100),
    rebalance_band: Decimal | None = Query(None, ge=0, le=1),
    require_sector: bool | None = Query(None),
    start: date | None = None,
    as_of: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RebalancePlanResponse:
    """Where this month's money goes to close the gaps (rule 34).

    The companion to `/rebalance`, which says how far the portfolio is
    from its targets. This says what to do about it with the contribution
    actually arriving, funding the largest gap first and stopping each
    allocation at the target rather than past it.

    ⚠️ **Nothing here sells.** Rule 34's priorities are all buy-side, and
    an overweight position is closed by dilution over later
    contributions: a sale realises tax on a portfolio whose thesis is
    compounding, and pays brokerage on both legs to move money the next
    contribution moves for free. Assets above target come back in
    `skipped` with `ABOVE_TARGET`.

    Distinct from `/contribution-plan`, which ranks by score to answer
    "where does new money do the most good". This ranks by gap to answer
    "what is furthest from where it should be". Same policy, two orders.

    Nothing is stored: the plan is derived from the ledger, the scores
    and the policy, exactly as positions are (rule 16).

    Reads only stored data (rule 23); prices, benchmarks and indicators
    must have been synced first.
    """
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)

    policy = _policy_with(
        max_asset_weight=max_asset_weight,
        max_sector_weight=max_sector_weight,
        max_positions=max_positions,
        min_ticket=min_ticket,
        min_coverage=min_coverage,
        min_score=min_score,
        rebalance_band=rebalance_band,
        require_sector=require_sector,
    )

    plan = plan_rebalance(
        db, portfolio, contribution=amount, start=start, as_of=as_of, policy=policy
    )

    return RebalancePlanResponse(
        portfolio_id=portfolio.id,
        rules_version=plan.rules_version,
        model_version=plan.model_version,
        formula_version=plan.formula_version,
        policy=_policy_response(plan.policy),
        contribution=plan.contribution,
        allocated=plan.allocated,
        unallocated=plan.unallocated,
        base_value=plan.base_value,
        underweight_before=plan.underweight_before,
        underweight_after=plan.underweight_after,
        allocations=[
            RebalanceAllocationResponse(
                ticker=item.ticker,
                asset_id=item.asset_id,
                name=item.name,
                sector=item.sector,
                amount=item.amount,
                rank=item.rank,
                merit_score=item.merit_score,
                current_weight=item.current_weight,
                target_weight=item.target_weight,
                weight_gap=item.weight_gap,
                needed=item.needed,
                limited_by=item.limited_by.value,
                weight_after=item.weight_after,
                gap_after=item.gap_after,
                detail=item.detail,
            )
            for item in plan.allocations
        ],
        skipped=[
            RebalanceSkippedResponse(
                ticker=item.ticker,
                asset_id=item.asset_id,
                name=item.name,
                reason=item.reason.value,
                detail=item.detail,
                current_weight=item.current_weight,
                target_weight=item.target_weight,
                weight_gap=item.weight_gap,
            )
            for item in plan.skipped
        ],
    )


def _policy_with(**overrides: object) -> AllocationPolicy:
    """The default policy with whatever the request actually set.

    Rule 32 requires every limit to be configurable, and `None` here
    means "not sent" rather than "no limit" — dropping the unset ones is
    what keeps an omitted parameter at its conservative default instead
    of clearing it.
    """
    given = {name: value for name, value in overrides.items() if value is not None}
    return replace(DEFAULT_POLICY, **given) if given else DEFAULT_POLICY


def _policy_response(policy: AllocationPolicy) -> AllocationPolicyResponse:
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


def _asset_score_response(asset: Asset, score: AssetScore) -> AssetScoreResponse:
    """One scored asset as the API reports it.

    Extracted for the same reason `_contribution_plan_response` is: the
    explanation endpoint must describe the very object the plain
    endpoint returns, not a second assembly of it.
    """
    return AssetScoreResponse(
        ticker=asset.ticker,
        asset_id=asset.id,
        name=asset.name,
        sector=asset.sector,
        formula_version=score.formula_version,
        final_score=score.final_score,
        coverage=score.coverage,
        sub_scores=[SubScoreResponse.model_validate(sub) for sub in score.sub_scores],
    )


# -- explanations (Wave 12) -------------------------------------------
#
# Every endpoint below computes its numbers exactly as the corresponding
# read endpoint does, hands them to `app.domain.ai` as a fact pack, and
# returns the prose together with the facts it was built from. The model
# never sees the database, never sees a series, and never produces a
# figure of its own (AGENTS.md rules 3/24, ADR-009).
#
# They are POSTs even though they store nothing. A GET is expected to be
# safe and repeatable, and these spend a metered external call and answer
# differently each time; labelling that as a read would be a lie a cache
# would eventually act on.


def _explain(provider: AIProvider, pack: FactPack) -> Explanation:
    """Run one explanation, translating provider failures into HTTP.

    Each failure keeps its own code, because the operator action differs:
    a missing key is a configuration fix, an unreachable model is a wait,
    and a refusal is neither. 503 for the two that may pass on their own,
    502 for the two where the provider answered and the answer was not
    usable.
    """
    try:
        return explain_facts(
            provider,
            pack,
            temperature=settings.AI_TEMPERATURE,
            max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        )
    except AINotConfiguredError as exc:
        raise _ai_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "AI_NOT_CONFIGURED", exc
        ) from exc
    except AIUnavailableError as exc:
        raise _ai_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "AI_UNAVAILABLE", exc
        ) from exc
    except AIResponseBlockedError as exc:
        raise _ai_http_error(
            status.HTTP_502_BAD_GATEWAY, "AI_RESPONSE_BLOCKED", exc
        ) from exc
    except InvalidAIResponseError as exc:
        raise _ai_http_error(
            status.HTTP_502_BAD_GATEWAY, "INVALID_AI_RESPONSE", exc
        ) from exc


def _ai_http_error(status_code: int, code: str, exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": str(exc)}},
    )


@router.post(
    "/{portfolio_id}/explain/performance",
    response_model=Explanation,
)
def explain_portfolio_performance(
    portfolio_id: int,
    benchmark: str = Query(
        "CDI", description="Benchmark code to explain the portfolio against."
    ),
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: AIProvider = Depends(get_ai_provider),
) -> Explanation:
    """Explain, in Portuguese, how this portfolio did against a benchmark.

    The numbers are the ones `GET /portfolios/{id}/benchmarks/{code}`
    returns — same call, same window, same figures — and they arrive at
    the model already rounded to the strings the screen shows, so the
    prose cannot disagree with the panel beside it.

    The window is the one **both** sides share and may be narrower than
    the portfolio's life (W11-004); the response says which it was.
    """
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    definition = _resolve_benchmark(benchmark)
    comparison = compare_portfolio_with_benchmark(db, portfolio, definition, start, end)

    pack = portfolio_performance_facts(
        portfolio.name,
        portfolio.id,
        BenchmarkComparisonResponse.model_validate(comparison),
    )
    return _explain(provider, pack)


@router.post(
    "/{portfolio_id}/explain/contribution-plan",
    response_model=Explanation,
)
def explain_contribution_plan(
    portfolio_id: int,
    amount: Decimal | None = Query(None, gt=0),
    max_asset_weight: Decimal | None = Query(None, gt=0, le=1),
    max_sector_weight: Decimal | None = Query(None, gt=0, le=1),
    max_share_per_position: Decimal | None = Query(None, gt=0, le=1),
    max_positions: int | None = Query(None, ge=1),
    min_ticket: Decimal | None = Query(None, ge=0),
    min_coverage: Decimal | None = Query(None, ge=0, le=1),
    min_score: Decimal | None = Query(None, ge=0, le=100),
    require_sector: bool | None = Query(None),
    start: date | None = None,
    as_of: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: AIProvider = Depends(get_ai_provider),
) -> Explanation:
    """Explain where the next contribution goes, and why.

    Takes the same policy overrides as
    `GET /portfolios/{id}/contribution-plan`, and for a reason: an
    investor who raised a ceiling and then asked for an explanation must
    get the plan they are looking at, not the default one.

    The model is told the amounts *and* the named rule that sized each
    line, so it never has to infer a reason — inferring one is how it
    would invent one.
    """
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    policy = _policy_with(
        max_asset_weight=max_asset_weight,
        max_sector_weight=max_sector_weight,
        max_share_per_position=max_share_per_position,
        max_positions=max_positions,
        min_ticket=min_ticket,
        min_coverage=min_coverage,
        min_score=min_score,
        require_sector=require_sector,
    )
    plan = plan_contribution(
        db,
        portfolio,
        contribution=amount,
        start=start,
        as_of=as_of,
        policy=policy,
    )

    pack = contribution_plan_facts(
        portfolio.name, _contribution_plan_response(portfolio.id, plan)
    )
    return _explain(provider, pack)


@router.post(
    "/{portfolio_id}/explain/scores/{ticker}",
    response_model=Explanation,
)
def explain_asset_score(
    portfolio_id: int,
    ticker: str,
    start: date | None = None,
    as_of: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: AIProvider = Depends(get_ai_provider),
) -> Explanation:
    """Explain one asset's score inside this portfolio.

    The score is relative to the portfolio (rule 31) and rests on
    whatever fraction of the formula had data, which is why `coverage`
    travels with it and the prompt requires it to be stated: two scores
    with different coverage are not comparable, and an explanation that
    omitted that would make them look as though they were.
    """
    portfolio = _get_owned_portfolio(db, portfolio_id, current_user)
    scored = score_universe(db, portfolio, start=start, as_of=as_of)

    wanted = ticker.upper()
    match = next(
        ((asset, score) for asset, score in scored if asset.ticker.upper() == wanted),
        None,
    )
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "ASSET_NOT_FOUND",
                    "message": f"{ticker} is not scored for this portfolio.",
                }
            },
        )

    asset, score = match
    pack = asset_score_facts(_asset_score_response(asset, score), portfolio.id)
    return _explain(provider, pack)
