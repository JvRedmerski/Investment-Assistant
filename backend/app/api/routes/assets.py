from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_fundamentals_provider,
    get_market_data_provider,
)
from app.data.database import get_db
from app.data.models.assets import Asset, AssetPrice
from app.data.models.fundamentals import FinancialIndicator, Fundamental
from app.data.models.users import User
from app.domain.assets.schemas import AssetCreate, AssetResponse
from app.domain.fundamentals.schemas import (
    FinancialIndicatorResponse,
    FundamentalResponse,
    FundamentalsSyncResponse,
    IndicatorsComputeResponse,
)
from app.domain.fundamentals.service import (
    compute_and_store_indicators,
    sync_annual_statements,
)
from app.domain.market_data.schemas import (
    AssetPriceResponse,
    PriceSyncRequest,
    PriceSyncResponse,
)
from app.domain.market_data.service import sync_daily_history
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.exceptions import (
    FundamentalsNotFoundError,
    FundamentalsUnavailableError,
    InvalidFundamentalsResponseError,
)
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)

router = APIRouter(prefix="/assets", tags=["Assets"])

_DEFAULT_SYNC_WINDOW_DAYS = 30


def _get_asset_by_ticker(db: Session, ticker: str) -> Asset:
    asset = db.query(Asset).filter(Asset.ticker == ticker.strip().upper()).first()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "ASSET_NOT_FOUND",
                    "message": f"Asset {ticker} was not found.",
                }
            },
        )
    return asset


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Asset:
    """Register a new asset for tracking (watch-only, no brokerage link)."""
    existing = db.query(Asset).filter(Asset.ticker == payload.ticker).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "ASSET_ALREADY_EXISTS",
                    "message": f"Asset {payload.ticker} is already registered.",
                }
            },
        )

    asset = Asset(
        ticker=payload.ticker,
        name=payload.name,
        asset_type=payload.asset_type,
        sector=payload.sector,
        currency=payload.currency,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetResponse])
def list_assets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Asset]:
    return db.query(Asset).order_by(Asset.ticker).all()


@router.get("/{ticker}", response_model=AssetResponse)
def get_asset(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Asset:
    return _get_asset_by_ticker(db, ticker)


@router.post("/{ticker}/prices/sync", response_model=PriceSyncResponse)
def sync_asset_prices(
    ticker: str,
    payload: PriceSyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> PriceSyncResponse:
    """Fetch daily OHLCV history from the market data provider and store it.

    This is the only endpoint that calls the external provider. Reading
    prices (`GET /{ticker}/prices`) always reads from the database, never
    from here implicitly (AGENTS.md rule 23).
    """
    asset = _get_asset_by_ticker(db, ticker)

    # Explicit UTC "today" (AGENTS.md rule 18 — never assume timezone
    # implicitly); B3-local-time nuances can be layered on later if needed.
    end = payload.end or datetime.now(UTC).date()
    start = payload.start or (end - timedelta(days=_DEFAULT_SYNC_WINDOW_DAYS))

    try:
        result = sync_daily_history(db, provider, asset, start, end)
    except TickerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "MARKET_DATA_TICKER_NOT_FOUND",
                    "message": f"Provider has no data for {asset.ticker}.",
                }
            },
        ) from exc
    except MarketDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "MARKET_DATA_UNAVAILABLE",
                    "message": "Market data provider is currently unavailable.",
                }
            },
        ) from exc
    except InvalidMarketDataResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "MARKET_DATA_INVALID_RESPONSE",
                    "message": "Market data provider returned an unparseable response.",
                }
            },
        ) from exc

    return PriceSyncResponse(
        ticker=result.ticker,
        start=result.start,
        end=result.end,
        fetched=result.fetched,
        inserted=result.inserted,
        skipped_existing=result.skipped_existing,
        rejected=result.rejected,
    )


@router.get("/{ticker}/prices", response_model=list[AssetPriceResponse])
def list_asset_prices(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AssetPrice]:
    """Read stored daily prices for an asset. Never queries the external
    provider (AGENTS.md rule 23) — use `POST /{ticker}/prices/sync` first.
    """
    asset = _get_asset_by_ticker(db, ticker)

    query = db.query(AssetPrice).filter(AssetPrice.asset_id == asset.id)
    if start is not None:
        query = query.filter(AssetPrice.date >= start)
    if end is not None:
        query = query.filter(AssetPrice.date <= end)

    return query.order_by(AssetPrice.date).all()


@router.post("/{ticker}/fundamentals/sync", response_model=FundamentalsSyncResponse)
def sync_asset_fundamentals(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: FundamentalsProvider = Depends(get_fundamentals_provider),
) -> FundamentalsSyncResponse:
    """Fetch annual financial statements from the fundamentals provider
    and store the ones not already held.

    Like the price sync, this is the only endpoint that calls the
    external provider; reading fundamentals never does (AGENTS.md rule
    23). Already-stored reference dates are kept as-is, never
    overwritten — see `app.domain.fundamentals.service`.
    """
    asset = _get_asset_by_ticker(db, ticker)

    try:
        result = sync_annual_statements(db, provider, asset)
    except FundamentalsNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "FUNDAMENTALS_NOT_FOUND",
                    "message": f"Provider has no fundamental data for {asset.ticker}.",
                }
            },
        ) from exc
    except FundamentalsUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "FUNDAMENTALS_UNAVAILABLE",
                    "message": "Fundamentals provider is currently unavailable.",
                }
            },
        ) from exc
    except InvalidFundamentalsResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "FUNDAMENTALS_INVALID_RESPONSE",
                    "message": (
                        "Fundamentals provider returned an unparseable response."
                    ),
                }
            },
        ) from exc

    return FundamentalsSyncResponse(
        ticker=result.ticker,
        fetched=result.fetched,
        inserted=result.inserted,
        skipped_existing=result.skipped_existing,
        rejected=result.rejected,
    )


@router.get("/{ticker}/fundamentals", response_model=list[FundamentalResponse])
def list_asset_fundamentals(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Fundamental]:
    """Read stored annual statements for an asset, oldest first. Never
    queries the external provider (AGENTS.md rule 23) — use
    `POST /{ticker}/fundamentals/sync` first.

    `start`/`end` filter on `reference_date`.
    """
    asset = _get_asset_by_ticker(db, ticker)

    query = db.query(Fundamental).filter(Fundamental.asset_id == asset.id)
    if start is not None:
        query = query.filter(Fundamental.reference_date >= start)
    if end is not None:
        query = query.filter(Fundamental.reference_date <= end)

    return query.order_by(Fundamental.reference_date).all()


@router.post("/{ticker}/indicators/compute", response_model=IndicatorsComputeResponse)
def compute_asset_indicators(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IndicatorsComputeResponse:
    """Derive fundamental indicators from data already stored.

    Unlike the `*/sync` endpoints, this **never contacts an external
    provider** — it only transforms stored statements and prices. Periods
    already computed are left untouched (ADR-013).
    """
    asset = _get_asset_by_ticker(db, ticker)
    result = compute_and_store_indicators(db, asset)

    return IndicatorsComputeResponse(
        ticker=result.ticker,
        periods=result.periods,
        computed=result.computed,
        skipped_existing=result.skipped_existing,
    )


@router.get("/{ticker}/indicators", response_model=list[FinancialIndicatorResponse])
def list_asset_indicators(
    ticker: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FinancialIndicator]:
    """Read stored indicators for an asset, oldest first.

    `start`/`end` filter on `reference_date`. A `null` indicator means it
    was not computable from the available data, never zero.
    """
    asset = _get_asset_by_ticker(db, ticker)

    query = db.query(FinancialIndicator).filter(FinancialIndicator.asset_id == asset.id)
    if start is not None:
        query = query.filter(FinancialIndicator.reference_date >= start)
    if end is not None:
        query = query.filter(FinancialIndicator.reference_date <= end)

    return query.order_by(FinancialIndicator.reference_date).all()
