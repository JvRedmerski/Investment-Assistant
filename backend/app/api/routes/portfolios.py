from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.data.database import get_db
from app.data.models.assets import Asset
from app.data.models.portfolio import Portfolio, Transaction, TransactionTypeEnum
from app.data.models.users import User
from app.domain.benchmarks.catalog import UnknownBenchmarkError, get_benchmark
from app.domain.benchmarks.schemas import BenchmarkComparisonResponse
from app.domain.benchmarks.service import compare_portfolio_with_benchmark
from app.domain.portfolio.schemas import (
    AssetPositionResponse,
    PortfolioCreate,
    PortfolioPositionsResponse,
    PortfolioResponse,
    PortfolioUpdate,
    TransactionCreate,
    TransactionResponse,
)
from app.domain.portfolio.service import (
    ZERO,
    compute_asset_quantity,
    compute_net_contributions,
    compute_positions,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioPositionsResponse:
    """Consolidated, cost-basis positions for a portfolio.

    Entirely derived from the transaction ledger (AGENTS.md rule 16); does
    not include current market value, which requires price data from the
    Market Data integration (Wave 05, not yet implemented).
    """
    _get_owned_portfolio(db, portfolio_id, current_user)

    transactions = (
        db.query(Transaction).filter(Transaction.portfolio_id == portfolio_id).all()
    )
    positions = compute_positions(transactions)

    tickers: dict[int, str] = {}
    if positions:
        assets = db.query(Asset).filter(Asset.id.in_(positions.keys())).all()
        tickers = {asset.id: asset.ticker for asset in assets}

    position_items = [
        AssetPositionResponse(
            asset_id=asset_id,
            ticker=tickers.get(asset_id, "UNKNOWN"),
            quantity=position.quantity,
            average_price=position.average_price,
            invested_amount=position.invested_amount,
            realized_pnl=position.realized_pnl,
            dividends_received=position.dividends_received,
        )
        for asset_id, position in sorted(positions.items())
    ]

    return PortfolioPositionsResponse(
        portfolio_id=portfolio_id,
        positions=position_items,
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

    comparison = compare_portfolio_with_benchmark(db, portfolio, definition, start, end)
    return BenchmarkComparisonResponse.model_validate(comparison)
