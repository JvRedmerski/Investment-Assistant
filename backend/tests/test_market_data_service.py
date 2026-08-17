"""Unit tests for sync_daily_history against a fake MarketDataProvider and
a throwaway in-memory SQLite session (no FastAPI/HTTP layer involved)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset, AssetPrice
from app.domain.market_data.service import sync_daily_history
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.schemas import DailyBar


class FakeProvider(MarketDataProvider):
    def __init__(self, bars):
        self._bars = bars

    def get_quote(self, ticker):  # pragma: no cover - unused in these tests
        raise NotImplementedError

    def get_daily_history(self, ticker, start, end):
        return [bar for bar in self._bars if start <= bar.date <= end]


def _bar(day: int, price: str = "38.50") -> DailyBar:
    return DailyBar(
        date=date(2026, 1, day),
        open=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        close=Decimal(price),
        adjusted_close=Decimal(price),
        volume=Decimal(1000),
    )


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def asset(db_session):
    asset = Asset(ticker="PETR4", name="Petrobras PN", asset_type="STOCK")
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def test_sync_inserts_all_bars_when_nothing_stored_yet(db_session, asset):
    provider = FakeProvider([_bar(2), _bar(3)])

    result = sync_daily_history(
        db_session, provider, asset, date(2026, 1, 1), date(2026, 1, 5)
    )

    assert result.fetched == 2
    assert result.inserted == 2
    assert result.skipped_existing == 0
    stored = db_session.query(AssetPrice).filter(AssetPrice.asset_id == asset.id).all()
    assert len(stored) == 2


def test_sync_skips_dates_already_stored(db_session, asset):
    db_session.add(
        AssetPrice(
            asset_id=asset.id,
            date=date(2026, 1, 2),
            open=Decimal(30),
            high=Decimal(30),
            low=Decimal(30),
            close=Decimal(30),
            adjusted_close=Decimal(30),
            volume=Decimal(1),
            source="brapi",
        )
    )
    db_session.commit()

    provider = FakeProvider([_bar(2, price="99.00"), _bar(3)])

    result = sync_daily_history(
        db_session, provider, asset, date(2026, 1, 1), date(2026, 1, 5)
    )

    assert result.fetched == 2
    assert result.inserted == 1
    assert result.skipped_existing == 1

    stored_jan_2 = (
        db_session.query(AssetPrice)
        .filter(AssetPrice.asset_id == asset.id, AssetPrice.date == date(2026, 1, 2))
        .one()
    )
    # The pre-existing row must not have been overwritten by the new fetch.
    assert stored_jan_2.close == Decimal(30)


def test_sync_is_idempotent_when_run_twice(db_session, asset):
    provider = FakeProvider([_bar(2), _bar(3)])

    sync_daily_history(db_session, provider, asset, date(2026, 1, 1), date(2026, 1, 5))
    second_result = sync_daily_history(
        db_session, provider, asset, date(2026, 1, 1), date(2026, 1, 5)
    )

    assert second_result.inserted == 0
    assert second_result.skipped_existing == 2
    stored = db_session.query(AssetPrice).filter(AssetPrice.asset_id == asset.id).all()
    assert len(stored) == 2


def test_sync_only_considers_bars_within_requested_window(db_session, asset):
    provider = FakeProvider([_bar(2), _bar(10)])

    result = sync_daily_history(
        db_session, provider, asset, date(2026, 1, 1), date(2026, 1, 5)
    )

    assert result.fetched == 1
    assert result.inserted == 1
