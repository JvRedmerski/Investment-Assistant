"""The `intraday_prices` column contract (W15-004).

These assert the schema itself rather than behaviour, because each column
here answers a rule or a measurement and a silent revert would be
invisible in every other test: a FLOAT price still stores, a naive
timestamp still stores, and a missing `source_window` would just mean
bars merge quietly.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset, IntradayPrice


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def asset(db_session):
    asset = Asset(ticker="PETR4", name="Petrobras PN", asset_type="STOCK")
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


_COLUMNS = IntradayPrice.__table__.columns


class TestPrecision:
    """Rule 17, deferred here by migration 002 and paid in migration 013."""

    def test_ohlc_is_numeric_not_float(self):
        for name in ("open", "high", "low", "close"):
            assert isinstance(_COLUMNS[name].type, sa.Numeric)
            assert not isinstance(_COLUMNS[name].type, sa.Float)

    def test_ohlc_carries_the_projects_money_precision(self):
        for name in ("open", "high", "low", "close"):
            assert (_COLUMNS[name].type.precision, _COLUMNS[name].type.scale) == (18, 6)

    def test_volume_stays_float_because_it_is_a_share_count(self):
        """The same call `asset_prices.volume` got: not a monetary value."""
        assert isinstance(_COLUMNS["volume"].type, sa.Float)


class TestTimezone:
    def test_the_timestamp_column_is_timezone_aware(self):
        """Rule 18. The only timestamp in this schema where the
        distinction changes an answer: a bar stamped 10:15 with no zone
        could be three different instants."""
        assert _COLUMNS["timestamp"].type.timezone is True

    def test_it_is_the_only_aware_column_on_this_table(self):
        """`created_at` is naive like every other audit stamp in the
        schema; changing that is a different decision, not this one."""
        assert _COLUMNS["created_at"].type.timezone is False


class TestTheWindowOnTheRow:
    def test_source_window_exists_and_is_required(self):
        """There is no honest default: a bar whose window is unknown
        cannot be shown to belong to either partition (ADR-036)."""
        assert _COLUMNS["source_window"].nullable is False

    def test_the_window_is_not_part_of_the_unique_key(self):
        """Admitting it would let one instant hold two rows, which is
        exactly the mixture the window exists to prevent."""
        unique = next(
            constraint
            for constraint in IntradayPrice.__table__.constraints
            if isinstance(constraint, sa.UniqueConstraint)
        )
        assert [column.name for column in unique.columns] == [
            "asset_id",
            "timestamp",
            "timeframe",
        ]


class TestItRoundTrips:
    def test_a_decimal_price_survives_storage(self, db_session, asset):
        db_session.add(
            IntradayPrice(
                asset_id=asset.id,
                timestamp=datetime(2026, 8, 18, 13, 15, tzinfo=UTC),
                timeframe="15m",
                open=Decimal("42.910000"),
                high=Decimal("42.960000"),
                low=Decimal("42.860000"),
                close=Decimal("42.890000"),
                volume=1161600.0,
                source_window="5d",
                source="brapi",
            )
        )
        db_session.commit()

        stored = db_session.query(IntradayPrice).one()
        assert stored.close == Decimal("42.890000")
        assert stored.source_window == "5d"
        assert stored.timeframe == "15m"
