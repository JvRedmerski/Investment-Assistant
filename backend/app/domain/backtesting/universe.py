"""The strategy under test: this project's own allocator, replayed.

The point of a backtest here is not to evaluate *a* strategy — it is to
evaluate **the** strategy, the one `/contribution-plan` runs today. So
this module builds no ranking of its own. It assembles the candidates as
they would have looked on a past date and hands them to
`allocation.allocate_contribution`, which is pure and is the same
function the live endpoint calls.

That reuse is what makes the result mean something. A backtest of a
reimplementation measures the reimplementation.

## Where the look-ahead is kept out

Three inputs could each leak the future, and each is cut at `as_of`:

- **Prices** — `score_asset` filters `AssetPrice.date <= as_of`, and the
  simulation only ever hands over the closes of the session it is on.
- **Fundamentals** — filtered by the *publication* rule rather than the
  reference date, because a fiscal year is not public on the day it
  ends (`availability`, rule 109).
- **The portfolio itself** — the exposure comes from the simulated
  positions on that date, not from any stored portfolio, so the
  Diversification pillar and the concentration ceilings read the
  portfolio the strategy actually built up to then.

The benchmark and the risk-free rate are loaded once per decision with
the same `as_of`, exactly as `score_universe` does for the live path.
"""

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models.assets import Asset
from app.domain.backtesting.availability import PUBLICATION_LAG_MONTHS
from app.domain.backtesting.schemas import Order, Side, SimulationState, Strategy
from app.domain.benchmarks.catalog import IBOVESPA
from app.domain.benchmarks.service import benchmark_price_points, risk_free_rate_for
from app.domain.portfolio.service import AssetPosition
from app.domain.recommendations.allocation import (
    DEFAULT_POLICY,
    AllocationPlan,
    AllocationPolicy,
    Candidate,
    allocate_contribution,
)
from app.domain.recommendations.service import PortfolioExposure, score_asset

ZERO = Decimal(0)


def exposure_from_positions(
    positions: Mapping[int, AssetPosition],
    sectors: Mapping[int, str | None],
) -> PortfolioExposure:
    """The simulated portfolio's concentration, in the shape scoring wants.

    Cost basis, like `build_exposure`, and for the same reason: the
    Diversification pillar and the allocator's ceilings are defined on
    what was paid, and mixing in market value here would make a backtest
    measure a different rule from the live plan (see Future Work on
    migrating both together).
    """
    invested = {
        asset_id: position.invested_amount
        for asset_id, position in positions.items()
        if position.quantity > ZERO and position.invested_amount > ZERO
    }
    total = sum(invested.values(), ZERO)
    if total <= ZERO:
        return PortfolioExposure(total_invested=ZERO, by_asset={}, by_sector={})

    by_asset = {asset_id: amount / total for asset_id, amount in invested.items()}
    by_sector: dict[str, Decimal] = {}
    for asset_id, weight in by_asset.items():
        sector = sectors.get(asset_id)
        if sector is not None:
            by_sector[sector] = by_sector.get(sector, ZERO) + weight

    return PortfolioExposure(
        total_invested=total, by_asset=by_asset, by_sector=by_sector
    )


def plan_on(
    db: Session,
    assets: Sequence[Asset],
    state: SimulationState,
    *,
    contribution: Decimal,
    start: date | None = None,
    policy: AllocationPolicy = DEFAULT_POLICY,
    publication_lag_months: int = PUBLICATION_LAG_MONTHS,
) -> AllocationPlan:
    """What the allocator would have decided on `state.day`.

    Everything it reads is cut at that date. Nothing is stored: a plan
    is derived here exactly as it is in production (rule 16).

    `assets` is both the universe offered and the source of the sector
    of everything held, which is sound because the simulation can only
    ever hold what this same list offered it. A held asset absent from
    it would have no sector here, and a sector ceiling that cannot see
    part of its own sector is not a ceiling.
    """
    sectors = {asset.id: asset.sector for asset in assets}
    exposure = exposure_from_positions(state.positions, sectors)

    benchmark = benchmark_price_points(db, IBOVESPA, start, state.day)
    risk_free = risk_free_rate_for(db, start, state.day)

    candidates = [
        Candidate(
            ticker=asset.ticker,
            asset_id=asset.id,
            name=asset.name,
            sector=asset.sector,
            score=score_asset(
                db,
                asset,
                exposure,
                start=start,
                as_of=state.day,
                benchmark=benchmark,
                risk_free_rate=risk_free,
                publication_lag_months=publication_lag_months,
            ),
            held_amount=exposure.amount_of(asset.id),
        )
        for asset in assets
    ]

    return allocate_contribution(
        candidates,
        invested=exposure.total_invested,
        sector_amounts=exposure.amounts_by_sector(),
        contribution=contribution,
        policy=policy,
    )


def contribution_strategy(
    db: Session,
    assets: Sequence[Asset],
    *,
    start: date | None = None,
    policy: AllocationPolicy = DEFAULT_POLICY,
    publication_lag_months: int = PUBLICATION_LAG_MONTHS,
) -> Strategy:
    """The project's contribution plan, as a strategy the engine can run.

    The money offered to the allocator is **all the cash on hand**, not
    the month's contribution: an unspent remainder and a dividend
    received since are the same money, and holding them back would make
    the backtest accumulate idle cash the real plan would have deployed.
    """

    def strategy(state: SimulationState) -> list[Order]:
        if state.cash <= ZERO:
            return []
        plan = plan_on(
            db,
            assets,
            state,
            contribution=state.cash,
            start=start,
            policy=policy,
            publication_lag_months=publication_lag_months,
        )
        return [
            Order(
                asset_id=allocation.asset_id,
                ticker=allocation.ticker,
                side=Side.BUY,
                amount=allocation.amount,
            )
            for allocation in plan.allocations
        ]

    return strategy
