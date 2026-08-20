from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_fundamentals_provider,
    get_historical_price_provider,
    get_market_data_provider,
)
from app.core.config import settings
from app.data.database import get_db
from app.data.models.assets import Asset, AssetPrice
from app.data.models.fundamentals import FinancialIndicator, Fundamental
from app.data.models.users import User
from app.domain.assets.schemas import AssetCreate, AssetResponse
from app.domain.benchmarks.catalog import UnknownBenchmarkError, get_benchmark
from app.domain.benchmarks.schemas import BenchmarkComparisonResponse
from app.domain.benchmarks.service import compare_asset_with_benchmark
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
    PriceBackfillRequest,
    PriceSyncRequest,
    PriceSyncResponse,
    QuoteResponse,
)
from app.domain.market_data.service import PriceSyncResult, sync_daily_history
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.exceptions import (
    FundamentalsNotFoundError,
    FundamentalsUnavailableError,
    InvalidFundamentalsResponseError,
)
from app.integrations.market_data.base import (
    DailyHistoryProvider,
    MarketDataProvider,
)
from app.integrations.market_data.exceptions import (
    HistoryWindowTooLargeError,
    InvalidMarketDataResponseError,
    MarketDataError,
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
    except MarketDataError as exc:
        raise _price_source_http_error(exc, asset.ticker) from exc

    return _as_sync_response(result)


@router.post("/{ticker}/prices/backfill", response_model=PriceSyncResponse)
def backfill_asset_prices(
    ticker: str,
    payload: PriceBackfillRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: DailyHistoryProvider = Depends(get_historical_price_provider),
) -> PriceSyncResponse:
    """Fill deep price history from the open historical archive.

    The sibling endpoint (`/prices/sync`) goes to the market data vendor,
    which quotes and adjusts but whose free plan serves a `3mo` range
    anchored at today — about 63 sessions, and no way to page further
    back. This one goes to B3's own published series: free, no quota, and
    decades deep. Its bars carry no adjusted close, and that absence is
    stored rather than faked (ADR-023).

    Both write to `asset_prices` and neither overwrites a date already
    there, so running one after the other is safe in any order.

    This can take minutes on a cold cache: the unit of retrieval is one
    file per calendar year covering every listed instrument, tens of
    megabytes each, downloaded once and then reused.
    """
    asset = _get_asset_by_ticker(db, ticker)

    end = payload.end or datetime.now(UTC).date()
    start = payload.start or date(settings.B3_COTAHIST_FIRST_YEAR, 1, 1)

    try:
        result = sync_daily_history(db, provider, asset, start, end)
    except MarketDataError as exc:
        raise _price_source_http_error(exc, asset.ticker) from exc

    return _as_sync_response(result)


def _as_sync_response(result: PriceSyncResult) -> PriceSyncResponse:
    return PriceSyncResponse(
        ticker=result.ticker,
        start=result.start,
        end=result.end,
        fetched=result.fetched,
        inserted=result.inserted,
        skipped_existing=result.skipped_existing,
        rejected=result.rejected,
    )


def _price_source_http_error(exc: MarketDataError, ticker: str) -> HTTPException:
    """Translate a price source failure into the standard error envelope.

    Shared by both ingestion routes so the vendor and the open archive
    fail the same way to a caller (rule 72); only the source behind them
    differs.
    """
    if isinstance(exc, HistoryWindowTooLargeError):
        # The caller asked for more history than the provider plan serves.
        # 400, not 502: the request is the thing that has to change, and
        # the message says by how much.
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MARKET_DATA_WINDOW_TOO_LARGE",
                    "message": str(exc),
                }
            },
        )
    if isinstance(exc, TickerNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "MARKET_DATA_TICKER_NOT_FOUND",
                    "message": f"Provider has no data for {ticker}.",
                }
            },
        )
    if isinstance(exc, InvalidMarketDataResponseError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "MARKET_DATA_INVALID_RESPONSE",
                    "message": "Market data provider returned an unparseable response.",
                }
            },
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": {
                "code": "MARKET_DATA_UNAVAILABLE",
                "message": "Market data provider is currently unavailable.",
            }
        },
    )


@router.get("/{ticker}/quote", response_model=QuoteResponse)
def get_asset_quote(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> QuoteResponse:
    """Fetch the latest quote for an asset from the market data provider.

    This calls the external provider on every request, deliberately: a
    quote that is served from cache is a stale number wearing a fresh
    timestamp. It is also why nothing here is stored - `asset_prices` holds
    closed daily sessions, and an intraday snapshot is a different quantity
    (the same reasoning as ADR-016 on `adjusted_close`).

    The asset must be registered first, so a typo cannot silently burn a
    request against the provider's monthly quota.
    """
    asset = _get_asset_by_ticker(db, ticker)

    try:
        quote = provider.get_quote(asset.ticker)
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

    return QuoteResponse(
        ticker=quote.ticker,
        price=quote.price,
        currency=quote.currency,
        as_of=quote.as_of,
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
    refill: bool = False,
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

    `?refill=true` fills columns that are **NULL** on periods already
    stored, and nothing else. It is how a database catches up when the
    code learns to read a figure the source was reporting all along —
    without it, every period ingested before this release would keep a
    permanently empty `dividends_paid`, and therefore no `dy`.
    """
    asset = _get_asset_by_ticker(db, ticker)

    try:
        result = sync_annual_statements(db, provider, asset, refill=refill)
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
        refilled=result.refilled,
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
    recompute: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IndicatorsComputeResponse:
    """Derive fundamental indicators from data already stored.

    Unlike the `*/sync` endpoints, this **never contacts an external
    provider** — it only transforms stored statements and prices.

    By default, periods already computed are left untouched. Pass
    `?recompute=true` to discard this asset's stored indicators and
    rebuild them — needed after a formula is corrected or a previously
    missing input is ingested. Raw statements are never affected
    (ADR-015).
    """
    asset = _get_asset_by_ticker(db, ticker)
    result = compute_and_store_indicators(db, asset, recompute=recompute)

    return IndicatorsComputeResponse(
        ticker=result.ticker,
        periods=result.periods,
        computed=result.computed,
        skipped_existing=result.skipped_existing,
        recomputed=result.recomputed,
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


@router.get("/{ticker}/benchmarks/{code}", response_model=BenchmarkComparisonResponse)
def compare_asset_against_benchmark(
    ticker: str,
    code: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BenchmarkComparisonResponse:
    """Compare one asset's stored price history against a benchmark.

    No cash flows are involved, so the asset's own adjusted-close series
    is already time-weighted and is used directly. Reads only stored data
    (AGENTS.md rule 23).
    """
    asset = _get_asset_by_ticker(db, ticker)
    try:
        definition = get_benchmark(code)
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

    comparison = compare_asset_with_benchmark(db, asset, definition, start, end)
    return BenchmarkComparisonResponse.model_validate(comparison)
