"""Unit tests for sync_annual_statements against a fake
FundamentalsProvider and a throwaway in-memory SQLite session (no
FastAPI/HTTP layer involved)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset
from app.data.models.fundamentals import Fundamental
from app.domain.fundamentals.service import sync_annual_statements
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.schemas import FinancialStatement


class FakeProvider(FundamentalsProvider):
    def __init__(self, statements):
        self._statements = statements
        self.calls = 0

    def get_annual_statements(self, ticker):
        self.calls += 1
        return list(self._statements)

    def close(self):  # pragma: no cover - nothing to release
        pass


def _statement(year: int, revenue: str = "100.5") -> FinancialStatement:
    return FinancialStatement(
        reference_date=date(year, 12, 31),
        revenue=Decimal(revenue),
        net_income=Decimal("10.25"),
        equity=Decimal("500.75"),
        debt=Decimal(300),
        cash=Decimal(60),
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


def _stored(db_session, asset):
    return (
        db_session.query(Fundamental)
        .filter(Fundamental.asset_id == asset.id)
        .order_by(Fundamental.reference_date)
        .all()
    )


def test_inserts_every_statement_when_store_is_empty(db_session, asset):
    provider = FakeProvider([_statement(2023), _statement(2024)])

    result = sync_annual_statements(db_session, provider, asset)

    assert (result.fetched, result.inserted, result.skipped_existing) == (2, 2, 0)
    assert result.rejected == 0
    assert [row.reference_date for row in _stored(db_session, asset)] == [
        date(2023, 12, 31),
        date(2024, 12, 31),
    ]


def test_stores_monetary_values_as_decimal_not_float(db_session, asset):
    sync_annual_statements(db_session, provider_for("100.5"), asset)

    (row,) = _stored(db_session, asset)
    assert isinstance(row.revenue, Decimal)
    assert row.revenue == Decimal("100.5")


def provider_for(revenue: str) -> FakeProvider:
    return FakeProvider([_statement(2024, revenue=revenue)])


def test_null_line_items_are_stored_as_null_not_zero(db_session, asset):
    provider = FakeProvider(
        [FinancialStatement(reference_date=date(2024, 12, 31), revenue=Decimal(1))]
    )

    sync_annual_statements(db_session, provider, asset)

    (row,) = _stored(db_session, asset)
    assert row.ebitda is None
    assert row.free_cash_flow is None
    assert row.revenue == Decimal(1)


def test_existing_reference_date_is_skipped_and_never_overwritten(db_session, asset):
    sync_annual_statements(db_session, FakeProvider([_statement(2024, "100")]), asset)

    result = sync_annual_statements(
        db_session, FakeProvider([_statement(2024, "999"), _statement(2023)]), asset
    )

    assert (result.fetched, result.inserted, result.skipped_existing) == (2, 1, 1)
    rows = _stored(db_session, asset)
    assert len(rows) == 2
    restated = next(r for r in rows if r.reference_date == date(2024, 12, 31))
    assert restated.revenue == Decimal(100), "a restatement must not overwrite"


def test_repeated_sync_is_idempotent(db_session, asset):
    provider = FakeProvider([_statement(2023), _statement(2024)])

    sync_annual_statements(db_session, provider, asset)
    result = sync_annual_statements(db_session, provider, asset)

    assert (result.inserted, result.skipped_existing) == (0, 2)
    assert len(_stored(db_session, asset)) == 2


def test_invalid_statement_is_rejected_and_never_persisted(db_session, asset):
    provider = FakeProvider(
        [
            _statement(2024),
            FinancialStatement(reference_date=date(2023, 12, 31), revenue=Decimal(-1)),
        ]
    )

    result = sync_annual_statements(db_session, provider, asset)

    assert (result.fetched, result.inserted, result.rejected) == (2, 1, 1)
    assert [row.reference_date for row in _stored(db_session, asset)] == [
        date(2024, 12, 31)
    ]


def test_duplicate_period_within_one_response_is_inserted_only_once(db_session, asset):
    # Both copies are rejected by the quality validator, so nothing is
    # stored — the ledger never ends up with two rows for one period.
    provider = FakeProvider([_statement(2024, "100"), _statement(2024, "200")])

    result = sync_annual_statements(db_session, provider, asset)

    assert result.rejected == 2
    assert result.inserted == 0
    assert _stored(db_session, asset) == []


def test_empty_provider_response_stores_nothing(db_session, asset):
    result = sync_annual_statements(db_session, FakeProvider([]), asset)

    assert (result.fetched, result.inserted, result.rejected) == (0, 0, 0)
    assert _stored(db_session, asset) == []
