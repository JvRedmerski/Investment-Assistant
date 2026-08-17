from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.data.database import get_db
from app.data.models.assets import Asset
from app.data.models.users import User
from app.domain.assets.schemas import AssetCreate, AssetResponse

router = APIRouter(prefix="/assets", tags=["Assets"])


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
