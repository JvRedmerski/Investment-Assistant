"""The database side of asset scoring.

Loads what each pillar needs and hands it to `scoring.py`, which is pure.
Nothing is calculated here — the same split `benchmarks/service.py` has
against `benchmarks/comparison.py`.

## Scoring is relative to a portfolio, not absolute

Rule 31 states the product's question as *"qual novo aporte melhora minha
carteira atual?"* and explicitly not *"qual ativo tem maior score?"*. The
Diversification pillar is where that lands: the same asset scores
differently for an investor who already holds 15% of it than for one who
holds none. So every entry point here takes a portfolio.

## Concentration is measured on cost basis, not market value

Weights come from `compute_positions`, which derives invested amount from
the ledger alone. That makes them available for any portfolio, with no
dependency on price coverage, and deterministic.

The more faithful measure of *current exposure* is market value, and it
is not used here because it would make the pillar absent for the whole
portfolio whenever a single held asset is missing a stored price — and
filling that gap is exactly what rule 44 forbids. For a buy-and-hold
portfolio taking monthly contributions the two track closely. The
market-value view arrives with the Wave 11 dashboard.

## Look-ahead

`as_of` truncates every series and selects the most recent indicator
dated on or before it (rules 108/109). A score for a past date must not
be able to see a statement published after it.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models.assets import Asset, AssetPrice
from app.data.models.fundamentals import FinancialIndicator
from app.data.models.portfolio import Portfolio, Transaction
from app.domain.benchmarks.catalog import IBOVESPA
from app.domain.benchmarks.service import benchmark_price_points, risk_free_rate_for
from app.domain.portfolio.service import compute_positions
from app.domain.recommendations.scoring import (
    AssetScore,
    compose,
    score_diversification,
    score_growth,
    score_quality,
    score_risk,
    score_valuation,
)
from app.quant.returns import PricePoint

ZERO = Decimal(0)


@dataclass(frozen=True)
class PortfolioExposure:
    """Cost-basis weights of a portfolio, by asset and by sector.

    Built once per scoring run: every asset in the universe is scored
    against the same exposure, and recomputing it per asset would be both
    wasteful and a chance for them to disagree.
    """

    total_invested: Decimal
    by_asset: dict[int, Decimal]
    by_sector: dict[str, Decimal]

    def weight_of(self, asset_id: int) -> Decimal:
        return self.by_asset.get(asset_id, ZERO)

    def weight_of_sector(self, sector: str | None) -> Decimal | None:
        """`None` when the asset has no sector recorded.

        Absent rather than zero: an unknown sector is not an empty one,
        and scoring it as empty would reward assets whose sector nobody
        filled in.
        """
        if sector is None:
            return None
        return self.by_sector.get(sector, ZERO)


def build_exposure(db: Session, portfolio: Portfolio) -> PortfolioExposure:
    """Current cost-basis concentration of `portfolio`."""
    transactions = (
        db.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).all()
    )
    positions = compute_positions(transactions)

    invested = {
        asset_id: position.invested_amount
        for asset_id, position in positions.items()
        if position.quantity > 0 and position.invested_amount > 0
    }
    total = sum(invested.values(), ZERO)
    if total <= 0:
        return PortfolioExposure(total_invested=ZERO, by_asset={}, by_sector={})

    sectors: dict[int, str | None] = {}
    if invested:
        for asset in db.query(Asset).filter(Asset.id.in_(invested)):
            sectors[asset.id] = asset.sector

    by_asset = {asset_id: amount / total for asset_id, amount in invested.items()}
    by_sector: dict[str, Decimal] = {}
    for asset_id, weight in by_asset.items():
        sector = sectors.get(asset_id)
        if sector is not None:
            by_sector[sector] = by_sector.get(sector, ZERO) + weight

    return PortfolioExposure(
        total_invested=total, by_asset=by_asset, by_sector=by_sector
    )


def score_asset(
    db: Session,
    asset: Asset,
    exposure: PortfolioExposure,
    start: date | None = None,
    as_of: date | None = None,
    benchmark: list[PricePoint] | None = None,
    risk_free_rate: Decimal | None = None,
) -> AssetScore:
    """Score one asset against one portfolio's exposure.

    `benchmark` and `risk_free_rate` are passed in so a whole universe
    can share one load of the Ibovespa and one CDI rate; `score_universe`
    does that. Omitted, they are fetched here.
    """
    if benchmark is None:
        benchmark = benchmark_price_points(db, IBOVESPA, start, as_of)
    if risk_free_rate is None:
        risk_free_rate = risk_free_rate_for(db, start, as_of)

    series = _price_series(db, asset, start, as_of)
    indicator = _latest_indicator(db, asset, as_of)

    return compose(
        [
            score_quality(
                roe=_decimal(indicator.roe if indicator else None),
                roic=_decimal(indicator.roic if indicator else None),
                net_margin=_decimal(indicator.net_margin if indicator else None),
            ),
            score_valuation(
                pe=_decimal(indicator.pe if indicator else None),
                pb=_decimal(indicator.pb if indicator else None),
            ),
            score_growth(
                revenue_growth=_decimal(
                    indicator.revenue_growth if indicator else None
                ),
                profit_growth=_decimal(indicator.profit_growth if indicator else None),
            ),
            score_risk(
                series,
                benchmark=benchmark,
                risk_free_rate=risk_free_rate,
                as_of=as_of,
            ),
            score_diversification(
                asset_weight=exposure.weight_of(asset.id),
                sector_weight=exposure.weight_of_sector(asset.sector),
            ),
        ]
    )


def score_universe(
    db: Session,
    portfolio: Portfolio,
    start: date | None = None,
    as_of: date | None = None,
) -> list[tuple[Asset, AssetScore]]:
    """Every tracked asset, scored against `portfolio`.

    Ordered by final score, best first, with unscorable assets last —
    they are still returned, because "this asset cannot be scored and
    here is what is missing" is an answer the investor needs, and
    dropping them would make the gap invisible.
    """
    exposure = build_exposure(db, portfolio)
    benchmark = benchmark_price_points(db, IBOVESPA, start, as_of)
    risk_free = risk_free_rate_for(db, start, as_of)

    scored = [
        (
            asset,
            score_asset(
                db,
                asset,
                exposure,
                start=start,
                as_of=as_of,
                benchmark=benchmark,
                risk_free_rate=risk_free,
            ),
        )
        for asset in db.query(Asset).filter(Asset.is_active.is_(True))
    ]

    # `ticker` breaks ties, so the order is total and reproducible
    # (rule 113) rather than depending on the database's row order.
    scored.sort(
        key=lambda pair: (
            pair[1].final_score is None,
            -(pair[1].final_score or ZERO),
            pair[0].ticker,
        )
    )
    return scored


# -- helpers ---------------------------------------------------------


def _price_series(
    db: Session, asset: Asset, start: date | None, as_of: date | None
) -> list[PricePoint]:
    query = db.query(AssetPrice).filter(AssetPrice.asset_id == asset.id)
    if start is not None:
        query = query.filter(AssetPrice.date >= start)
    if as_of is not None:
        query = query.filter(AssetPrice.date <= as_of)
    return [
        PricePoint(date=row.date, adjusted_close=row.adjusted_close)
        for row in query.order_by(AssetPrice.date)
    ]


def _latest_indicator(
    db: Session, asset: Asset, as_of: date | None
) -> FinancialIndicator | None:
    """The most recent indicator set dated on or before `as_of`.

    Never a later one, however much more complete it might be: a score
    for a past date that reads a statement published after it is
    look-ahead (rule 108).
    """
    query = db.query(FinancialIndicator).filter(FinancialIndicator.asset_id == asset.id)
    if as_of is not None:
        query = query.filter(FinancialIndicator.reference_date <= as_of)
    return query.order_by(FinancialIndicator.reference_date.desc()).first()


def _decimal(value: float | None) -> Decimal | None:
    """Indicators are stored as `float` (ADR-003); scoring is `Decimal`.

    Via `str`, so the conversion takes the decimal value that was stored
    rather than the binary expansion around it.
    """
    if value is None:
        return None
    return Decimal(str(value))
