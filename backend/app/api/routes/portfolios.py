from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.data.database import get_db
from app.data.models.portfolio import Portfolio
from app.data.models.users import User
from app.domain.portfolio.schemas import (
    PortfolioCreate,
    PortfolioResponse,
    PortfolioUpdate,
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
