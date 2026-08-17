from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base, utc_now
from app.data.models import (
    Asset,
    AssetPrice,
    InvestorProfile,
    Portfolio,
    RiskProfileEnum,
    Transaction,
    TransactionTypeEnum,
    User,
)


def test_models_creation_in_memory():
    # Use in-memory SQLite for testing model schema integrity
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()

    # 1. Create User & Profile
    user = User(email="test@investor.com", password_hash="hashed_pw_123")
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = InvestorProfile(
        user_id=user.id,
        risk_profile=RiskProfileEnum.CONSERVATIVE,
        monthly_contribution=1000.0,
    )
    db.add(profile)
    db.commit()

    # 2. Create Asset & AssetPrice
    asset = Asset(
        ticker="PETR4",
        name="Petróleo Brasileiro S.A.",
        asset_type="STOCK",
        sector="Oil & Gas",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    price = AssetPrice(
        asset_id=asset.id,
        date=date(2026, 8, 8),
        open=38.50,
        high=39.20,
        low=38.10,
        close=39.00,
        adjusted_close=39.00,
        volume=1500000.0,
    )
    db.add(price)
    db.commit()

    # 3. Create Portfolio & Transaction
    portfolio = Portfolio(user_id=user.id, name="Carteira Conservadora 2026")
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    tx = Transaction(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        type=TransactionTypeEnum.BUY,
        quantity=100.0,
        price=38.50,
        fees=5.0,
        transaction_date=utc_now(),
    )
    db.add(tx)
    db.commit()

    # 4. Assertions
    assert user.id is not None
    assert user.profile.risk_profile == RiskProfileEnum.CONSERVATIVE
    assert asset.ticker == "PETR4"
    assert len(portfolio.transactions) == 1
    assert portfolio.transactions[0].quantity == 100.0

    # Monetary/quantity columns must round-trip as Decimal, not float
    # (AGENTS.md rule 17: never use float indiscriminately for critical
    # monetary values).
    assert isinstance(portfolio.transactions[0].quantity, Decimal)
    assert isinstance(portfolio.transactions[0].price, Decimal)
    assert isinstance(price.close, Decimal)

    db.close()
