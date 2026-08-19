"""What happens to a bar whose source publishes no adjusted close.

Two sources now feed `asset_prices` and only one of them adjusts, so the
same missing field means two different things (ADR-023):

- the vendor has not published the adjustment *yet* — reject, and the
  next sync picks the date up complete (ADR-016);
- B3's COTAHIST never publishes one — store it, with the absence
  recorded, because rejecting would discard decades of open history.

These tests pin both halves, plus the rule that keeps the nullable
column safe: an unadjusted row never reaches a return series.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset, AssetPrice
from app.domain.market_data.series import (
    adjusted_closes_by_asset,
    adjusted_price_points,
)
from app.domain.market_data.service import sync_daily_history
from app.integrations.market_data.base import DailyHistoryProvider
from app.integrations.market_data.data_quality import validate_daily_bars
from app.integrations.market_data.schemas import DailyBar


class AdjustingSource(DailyHistoryProvider):
    """Stands in for the vendor: it adjusts, sometimes a session late."""

    source_name = "brapi"
    reports_adjusted_close = True

    def __init__(self, bars):
        self._bars = bars

    def get_daily_history(self, ticker, start, end):
        return [bar for bar in self._bars if start <= bar.date <= end]


class TradedPriceSource(DailyHistoryProvider):
    """Stands in for COTAHIST: it prints what traded and adjusts nothing."""

    source_name = "b3_cotahist"
    reports_adjusted_close = False

    def __init__(self, bars):
        self._bars = bars

    def get_daily_history(self, ticker, start, end):
        return [bar for bar in self._bars if start <= bar.date <= end]


def bar(day: int, close: str, adjusted: str | None) -> DailyBar:
    return DailyBar(
        date=date(2024, 5, day),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        adjusted_close=Decimal(adjusted) if adjusted is not None else None,
        volume=Decimal(1000),
    )


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def asset(db_session):
    asset = Asset(ticker="MGLU3", name="Magazine Luiza", asset_type="STOCK")
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


# -- the validator tells the two absences apart ------------------------


def test_an_adjusting_source_still_has_its_unadjusted_bar_rejected():
    report = validate_daily_bars(
        [bar(24, "1.32", None)], source_reports_adjusted_close=True
    )

    # ADR-016 unchanged: the value arrives next session, and storing now
    # would freeze the gap, since a stored date is never rewritten.
    assert report.valid_bars == []
    assert [issue.code for issue in report.errors] == ["MISSING_ADJUSTED_CLOSE"]


def test_a_source_that_never_adjusts_has_its_bar_accepted():
    report = validate_daily_bars(
        [bar(24, "1.32", None)], source_reports_adjusted_close=False
    )

    # Rejecting here would throw away the whole series to guard against a
    # publication lag this source does not have.
    assert len(report.valid_bars) == 1
    assert report.errors == []


def test_the_default_still_demands_an_adjusted_close():
    # Callers that predate the argument keep the stricter behaviour.
    report = validate_daily_bars([bar(24, "1.32", None)])

    assert report.valid_bars == []


def test_the_other_quality_checks_still_run_on_an_unadjusted_bar():
    broken = DailyBar(
        date=date(2024, 5, 24),
        open=Decimal("1.32"),
        high=Decimal("1.00"),  # high below open
        low=Decimal("1.30"),
        close=Decimal("1.32"),
        adjusted_close=None,
        volume=Decimal(1000),
    )

    report = validate_daily_bars([broken], source_reports_adjusted_close=False)

    # Waiving the adjusted-close rule must not waive OHLC consistency.
    assert [issue.code for issue in report.errors] == ["INVALID_OHLC"]


def test_a_non_positive_price_is_still_rejected_without_an_adjusted_close():
    zeroed = DailyBar(
        date=date(2024, 5, 24),
        open=Decimal(0),
        high=Decimal(0),
        low=Decimal(0),
        close=Decimal(0),
        adjusted_close=None,
        volume=Decimal(1000),
    )

    report = validate_daily_bars([zeroed], source_reports_adjusted_close=False)

    assert [issue.code for issue in report.errors] == ["NON_POSITIVE_PRICE"]


# -- ingestion ---------------------------------------------------------


def test_traded_prices_are_stored_with_the_absence_recorded(db_session, asset):
    provider = TradedPriceSource([bar(24, "1.32", None), bar(27, "13.15", None)])

    result = sync_daily_history(
        db_session, provider, asset, date(2024, 5, 1), date(2024, 5, 31)
    )

    assert result.inserted == 2
    assert result.rejected == 0
    rows = db_session.query(AssetPrice).order_by(AssetPrice.date).all()
    assert [row.close for row in rows] == [Decimal("1.32"), Decimal("13.15")]
    # Not filled from `close`: the column says the source computed none.
    assert [row.adjusted_close for row in rows] == [None, None]


def test_the_stored_row_names_the_source_it_came_from(db_session, asset):
    sync_daily_history(
        db_session,
        TradedPriceSource([bar(24, "1.32", None)]),
        asset,
        date(2024, 5, 1),
        date(2024, 5, 31),
    )

    (row,) = db_session.query(AssetPrice).all()
    # Two sources feed one table and only one of them adjusts, so a row
    # that does not say where it came from cannot be interpreted.
    assert row.source == "b3_cotahist"


def test_a_vendor_bar_is_still_stamped_with_the_vendor(db_session, asset):
    sync_daily_history(
        db_session,
        AdjustingSource([bar(24, "1.32", "1.30")]),
        asset,
        date(2024, 5, 1),
        date(2024, 5, 31),
    )

    (row,) = db_session.query(AssetPrice).all()
    assert row.source == "brapi"
    assert row.adjusted_close == Decimal("1.30")


def test_a_vendor_bar_without_adjustment_is_still_not_stored(db_session, asset):
    result = sync_daily_history(
        db_session,
        AdjustingSource([bar(24, "1.32", None)]),
        asset,
        date(2024, 5, 1),
        date(2024, 5, 31),
    )

    assert result.inserted == 0
    assert result.rejected == 1
    assert db_session.query(AssetPrice).count() == 0


# -- the rule that keeps the nullable column safe ----------------------


def test_an_unadjusted_row_never_enters_a_return_series():
    rows = [
        AssetPrice(asset_id=1, date=date(2024, 5, 24), close=Decimal("1.32")),
        AssetPrice(
            asset_id=1,
            date=date(2024, 5, 27),
            close=Decimal("13.15"),
            adjusted_close=Decimal("13.15"),
        ),
    ]

    points = adjusted_price_points(rows)

    # Magazine Luiza's real 1:10 reverse split sits between these two
    # dates. Letting the raw 1.32 in as an adjusted close would hand the
    # quant engine a +896% session that never happened to a holder.
    assert [point.date for point in points] == [date(2024, 5, 27)]


def test_price_points_come_back_in_date_order():
    rows = [
        AssetPrice(
            asset_id=1,
            date=date(2024, 5, 27),
            close=Decimal("13.15"),
            adjusted_close=Decimal("13.15"),
        ),
        AssetPrice(
            asset_id=1,
            date=date(2024, 5, 24),
            close=Decimal("1.32"),
            adjusted_close=Decimal("1.30"),
        ),
    ]

    points = adjusted_price_points(rows)

    assert [point.date for point in points] == [date(2024, 5, 24), date(2024, 5, 27)]


def test_a_series_with_no_adjusted_row_at_all_is_empty_not_fabricated():
    rows = [AssetPrice(asset_id=1, date=date(2024, 5, 24), close=Decimal("1.32"))]

    # An empty series makes every risk metric report absent, which is the
    # state the scoring engine was built to treat as normal — unlike a
    # confident number computed from the wrong prices.
    assert adjusted_price_points(rows) == []


def test_valuing_many_assets_skips_the_dates_it_cannot_value():
    rows = [
        AssetPrice(asset_id=1, date=date(2024, 5, 24), close=Decimal("1.32")),
        AssetPrice(
            asset_id=1,
            date=date(2024, 5, 27),
            close=Decimal("13.15"),
            adjusted_close=Decimal("13.15"),
        ),
        AssetPrice(
            asset_id=2,
            date=date(2024, 5, 24),
            close=Decimal("37.78"),
            adjusted_close=Decimal("37.50"),
        ),
    ]

    closes = adjusted_closes_by_asset(rows)

    assert closes == {
        1: {date(2024, 5, 27): Decimal("13.15")},
        2: {date(2024, 5, 24): Decimal("37.50")},
    }


def test_an_asset_with_only_unadjusted_rows_is_absent_not_empty_valued():
    rows = [AssetPrice(asset_id=1, date=date(2024, 5, 24), close=Decimal("1.32"))]

    # No key at all, rather than an asset mapped to an empty dict: the
    # difference matters to callers that test membership.
    assert adjusted_closes_by_asset(rows) == {}
