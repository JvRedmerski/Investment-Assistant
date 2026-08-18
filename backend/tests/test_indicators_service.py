"""Unit tests for compute_and_store_indicators against a throwaway
in-memory SQLite session. No provider is involved at all — this code path
must never touch the network."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset, AssetPrice
from app.data.models.fundamentals import FinancialIndicator, Fundamental
from app.domain.fundamentals.service import (
    _price_on_or_before,
    compute_and_store_indicators,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def asset(db_session):
    asset = Asset(ticker="PETR4", name="Petrobras PN", asset_type="STOCK")
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _add_statement(db_session, asset, year, revenue="1000", net_income="150", **extra):
    values = {
        "revenue": Decimal(revenue),
        "net_income": Decimal(net_income),
        "equity": Decimal(600),
        "debt": Decimal(400),
        "cash": Decimal(100),
    }
    values.update(extra)
    db_session.add(
        Fundamental(asset_id=asset.id, reference_date=date(year, 12, 31), **values)
    )
    db_session.commit()


def _add_price(db_session, asset, on: date, close: str):
    price = Decimal(close)
    db_session.add(
        AssetPrice(
            asset_id=asset.id,
            date=on,
            open=price,
            high=price,
            low=price,
            close=price,
            adjusted_close=price,
            volume=1000,
        )
    )
    db_session.commit()


def _stored(db_session, asset):
    return (
        db_session.query(FinancialIndicator)
        .filter(FinancialIndicator.asset_id == asset.id)
        .order_by(FinancialIndicator.reference_date)
        .all()
    )


def test_computes_one_row_per_stored_statement(db_session, asset):
    _add_statement(db_session, asset, 2023)
    _add_statement(db_session, asset, 2024)

    result = compute_and_store_indicators(db_session, asset)

    assert (result.periods, result.computed, result.skipped_existing) == (2, 2, 0)
    assert [row.reference_date for row in _stored(db_session, asset)] == [
        date(2023, 12, 31),
        date(2024, 12, 31),
    ]


def test_growth_uses_the_chronologically_previous_period(db_session, asset):
    _add_statement(db_session, asset, 2023, revenue="800")
    _add_statement(db_session, asset, 2024, revenue="1000")

    compute_and_store_indicators(db_session, asset)

    older, newer = _stored(db_session, asset)
    assert older.revenue_growth is None, "the first period has no predecessor"
    assert newer.revenue_growth == 0.25


def test_indicators_blocked_by_missing_inputs_are_stored_as_null(db_session, asset):
    _add_statement(db_session, asset, 2024)

    compute_and_store_indicators(db_session, asset)

    (row,) = _stored(db_session, asset)
    assert row.roe == 0.25
    assert row.net_margin == 0.15
    # No shares outstanding, no dividends, no EBIT, no EBITDA yet.
    assert row.pe is None
    assert row.pb is None
    assert row.dy is None
    assert row.roic is None
    assert row.debt_ebitda is None
    assert row.ebitda_margin is None


def test_existing_period_is_skipped_and_not_recomputed(db_session, asset):
    _add_statement(db_session, asset, 2024)
    compute_and_store_indicators(db_session, asset)
    (row,) = _stored(db_session, asset)
    row.roe = 0.999  # stand in for a previously stored value
    db_session.commit()

    result = compute_and_store_indicators(db_session, asset)

    assert (result.computed, result.skipped_existing) == (0, 1)
    (unchanged,) = _stored(db_session, asset)
    assert unchanged.roe == 0.999


def test_repeated_compute_is_idempotent(db_session, asset):
    _add_statement(db_session, asset, 2023)
    _add_statement(db_session, asset, 2024)

    compute_and_store_indicators(db_session, asset)
    result = compute_and_store_indicators(db_session, asset)

    assert (result.computed, result.skipped_existing) == (0, 2)
    assert len(_stored(db_session, asset)) == 2


def test_a_skipped_period_still_serves_as_the_growth_baseline(db_session, asset):
    # 2023 already computed; 2024 arrives later. 2024's growth must still
    # compare against 2023 even though 2023 was not recomputed.
    _add_statement(db_session, asset, 2023, revenue="800")
    compute_and_store_indicators(db_session, asset)

    _add_statement(db_session, asset, 2024, revenue="1000")
    result = compute_and_store_indicators(db_session, asset)

    assert (result.computed, result.skipped_existing) == (1, 1)
    newer = _stored(db_session, asset)[-1]
    assert newer.revenue_growth == 0.25


def test_roic_is_produced_from_the_stored_income_detail(db_session, asset):
    _add_statement(
        db_session,
        asset,
        2024,
        ebit=Decimal(300),
        income_before_tax=Decimal(1000),
        income_tax_expense=Decimal(-340),
    )

    compute_and_store_indicators(db_session, asset)

    (row,) = _stored(db_session, asset)
    # NOPAT = 300 * (1 - 340/1000) = 198; invested = 400 + 600 - 100 = 900
    assert row.roic == 0.22


def test_ebitda_indicators_stay_null_because_ebitda_is_never_ingested(
    db_session, asset
):
    _add_statement(db_session, asset, 2024, ebit=Decimal(300))

    compute_and_store_indicators(db_session, asset)

    (row,) = _stored(db_session, asset)
    assert row.debt_ebitda is None
    assert row.ebitda_margin is None


# -- recomputation (ADR-015) -------------------------------------------


def test_recompute_rebuilds_rows_from_current_inputs(db_session, asset):
    _add_statement(db_session, asset, 2024)
    compute_and_store_indicators(db_session, asset)
    (before,) = _stored(db_session, asset)
    assert before.roic is None, "no income detail stored yet"

    # The input that was missing arrives later.
    stored_statement = db_session.query(Fundamental).one()
    stored_statement.ebit = Decimal(300)
    stored_statement.income_before_tax = Decimal(1000)
    stored_statement.income_tax_expense = Decimal(-340)
    db_session.commit()

    result = compute_and_store_indicators(db_session, asset, recompute=True)

    assert result.recomputed is True
    assert (result.computed, result.skipped_existing) == (1, 0)
    rows = _stored(db_session, asset)
    assert len(rows) == 1, "rebuilt, not duplicated"
    assert rows[0].roic == 0.22, "the stale None was replaced by the new value"


def test_recompute_without_it_leaves_a_stale_row_untouched(db_session, asset):
    _add_statement(db_session, asset, 2024)
    compute_and_store_indicators(db_session, asset)
    stored_statement = db_session.query(Fundamental).one()
    stored_statement.ebit = Decimal(300)
    stored_statement.income_before_tax = Decimal(1000)
    stored_statement.income_tax_expense = Decimal(-340)
    db_session.commit()

    result = compute_and_store_indicators(db_session, asset)

    assert (result.computed, result.skipped_existing) == (0, 1)
    (row,) = _stored(db_session, asset)
    assert row.roic is None, "default behaviour never rewrites a stored indicator"


def test_recompute_does_not_touch_the_raw_statements(db_session, asset):
    _add_statement(db_session, asset, 2023)
    _add_statement(db_session, asset, 2024)
    compute_and_store_indicators(db_session, asset)

    compute_and_store_indicators(db_session, asset, recompute=True)

    # Reported facts survive a recomputation of derived values (ADR-015).
    assert db_session.query(Fundamental).count() == 2


def test_recompute_on_an_asset_with_no_indicators_yet_is_harmless(db_session, asset):
    _add_statement(db_session, asset, 2024)

    result = compute_and_store_indicators(db_session, asset, recompute=True)

    assert (result.computed, result.skipped_existing) == (1, 0)
    assert len(_stored(db_session, asset)) == 1


def test_asset_without_statements_computes_nothing(db_session, asset):
    result = compute_and_store_indicators(db_session, asset)

    assert (result.periods, result.computed) == (0, 0)
    assert _stored(db_session, asset) == []


# -- price selection: no look-ahead ------------------------------------


def test_price_after_the_reference_date_is_never_used(db_session, asset):
    _add_statement(db_session, asset, 2024)
    _add_price(db_session, asset, date(2024, 12, 30), "25")
    _add_price(db_session, asset, date(2025, 3, 10), "99")  # must be ignored

    compute_and_store_indicators(db_session, asset)

    # pe/pb are still None (no shares outstanding), so assert on the
    # selected price directly through the price-selection helper.
    assert _price_on_or_before(db_session, asset.id, date(2024, 12, 31)) == Decimal(25)


def test_price_exactly_on_the_reference_date_is_used(db_session, asset):
    _add_price(db_session, asset, date(2024, 12, 31), "27")
    _add_price(db_session, asset, date(2024, 12, 30), "25")

    assert _price_on_or_before(db_session, asset.id, date(2024, 12, 31)) == Decimal(27)


def test_price_is_none_when_only_later_prices_exist(db_session, asset):
    _add_price(db_session, asset, date(2025, 1, 5), "30")

    assert _price_on_or_before(db_session, asset.id, date(2024, 12, 31)) is None


def test_price_lookup_is_scoped_to_the_asset(db_session, asset):
    other = Asset(ticker="VALE3", name="Vale ON", asset_type="STOCK")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    _add_price(db_session, other, date(2024, 12, 30), "70")

    assert _price_on_or_before(db_session, asset.id, date(2024, 12, 31)) is None
