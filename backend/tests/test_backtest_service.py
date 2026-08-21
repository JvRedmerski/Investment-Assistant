"""Tests for the backtest service against a throwaway session (W13-005).

No provider is involved: a backtest reads stored data and nothing else
(rule 23). What is exercised here is the part the pure engine cannot be
asked about — which assets can be replayed at all, from when, and what
the two curves say once they can.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset, AssetPrice
from app.data.models.assets import CorporateAction as StoredAction
from app.data.models.fundamentals import FinancialIndicator
from app.domain.backtesting.schemas import CostModel
from app.domain.backtesting.service import (
    NO_PRICES,
    NO_TOTAL_RETURN_SERIES,
    BacktestSettings,
    run_backtest,
)
from app.domain.benchmarks.catalog import IBOVESPA

ZERO = Decimal(0)
FIRST = date(2024, 1, 1)
LAST = date(2025, 12, 31)


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


def _asset(db_session, ticker: str, sector: str = "Energia") -> Asset:
    asset = Asset(ticker=ticker, name=ticker, asset_type="STOCK", sector=sector)
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _indicators(db_session, asset: Asset, year: int = 2023) -> None:
    db_session.add(
        FinancialIndicator(
            asset_id=asset.id,
            reference_date=date(year, 12, 31),
            roe=Decimal("0.20"),
            roic=Decimal("0.15"),
            net_margin=Decimal("0.20"),
            pe=Decimal(5),
            pb=Decimal("0.5"),
            revenue_growth=Decimal("0.20"),
            profit_growth=Decimal("0.20"),
        )
    )
    db_session.commit()


def _prices(
    db_session,
    asset: Asset,
    close: str = "10",
    first: date = FIRST,
    days: int = 730,
    adjusted_from: date | None = FIRST,
) -> None:
    """A flat series, adjusted only from `adjusted_from` onwards.

    `adjusted_from=None` stores no adjusted close at all — an asset with
    prices and no total-return series, which is the state PRICE-001 left
    every asset in until its corporate actions were sized.
    """
    price = Decimal(close)
    for offset in range(days):
        day = first + timedelta(days=offset)
        db_session.add(
            AssetPrice(
                asset_id=asset.id,
                date=day,
                open=price,
                high=price,
                low=price,
                close=price,
                adjusted_close=(
                    price
                    if adjusted_from is not None and day >= adjusted_from
                    else None
                ),
                volume=1000,
            )
        )
    db_session.commit()


def _settings(**overrides) -> BacktestSettings:
    values = {
        "start": FIRST,
        "end": LAST,
        "strategy": "contribution-plan",
        "contribution": Decimal(1000),
        "day_of_month": 5,
    }
    values.update(overrides)
    return BacktestSettings(**values)


# -- what can be replayed ---------------------------------------------


def test_an_asset_with_no_stored_price_is_excluded_by_name(db_session):
    """It could only ever produce NO_PRICE fills; saying so is the answer."""
    priced = _asset(db_session, "AAA3")
    _prices(db_session, priced)
    _indicators(db_session, priced)
    unpriced = _asset(db_session, "BBB3", sector="Financeiro")
    _indicators(db_session, unpriced)

    result = run_backtest(db_session, [priced, unpriced], _settings())

    assert result.universe == ("AAA3",)
    assert result.excluded == (("BBB3", NO_PRICES),)


def test_an_asset_with_no_total_return_series_is_excluded_rather_than_ending_the_run(
    db_session,
):
    """Keeping it would make every backtest impossible, not one smaller."""
    good = _asset(db_session, "AAA3")
    _prices(db_session, good)
    _indicators(db_session, good)
    raw_only = _asset(db_session, "BBB3", sector="Financeiro")
    _prices(db_session, raw_only, adjusted_from=None)
    _indicators(db_session, raw_only)

    result = run_backtest(db_session, [good, raw_only], _settings())

    assert result.universe == ("AAA3",)
    assert result.excluded == (("BBB3", NO_TOTAL_RETURN_SERIES),)


def test_the_window_starts_where_the_last_asset_became_measurable(db_session):
    """The conservative bound, and it names what moved it.

    BBB3's adjusted series starts in July 2024, so a run over the whole
    period would be simulating six months in which a distribution this
    project cannot size may have gone unpaid — a wrong run, not merely an
    unmeasurable one.
    """
    early = _asset(db_session, "AAA3")
    _prices(db_session, early)
    _indicators(db_session, early)
    late = _asset(db_session, "BBB3", sector="Financeiro")
    _prices(db_session, late, adjusted_from=date(2024, 7, 1))
    _indicators(db_session, late)

    result = run_backtest(db_session, [early, late], _settings())

    assert result.window.requested_start == FIRST
    assert result.window.start == date(2024, 7, 1)
    assert result.window.bounded_by == "BBB3"


def test_a_window_the_data_supports_is_left_alone(db_session):
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    _indicators(db_session, asset)

    result = run_backtest(db_session, [asset], _settings())

    assert result.window.start == FIRST
    assert result.window.bounded_by is None


def test_a_series_interrupted_and_resumed_counts_from_after_the_gap(db_session):
    """Adjusted, interrupted, adjusted again is not a total-return series.

    The vendor's own figures for recent sessions can sit above sessions
    nobody ever derived. The part before the last gap holds values and is
    still not a series a return may be measured on.
    """
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    hole = db_session.query(AssetPrice).filter(
        AssetPrice.date >= date(2024, 6, 1), AssetPrice.date <= date(2024, 6, 3)
    )
    for row in hole:
        row.adjusted_close = None
    db_session.commit()

    result = run_backtest(db_session, [asset], _settings())

    assert result.window.start == date(2024, 6, 4)


def test_a_universe_nothing_can_be_tested_in_reports_rather_than_returning_zeros(
    db_session,
):
    asset = _asset(db_session, "AAA3")
    _indicators(db_session, asset)

    result = run_backtest(db_session, [asset], _settings())

    assert result.universe == ()
    assert result.excluded == (("AAA3", NO_PRICES),)
    assert result.wealth == ()
    assert result.index == ()
    assert result.trades.trades == 0


# -- what the run reports ---------------------------------------------


def test_a_flat_market_returns_the_contributions_and_nothing_more(db_session):
    """Two years of R$ 1.000 a month at an unchanging price.

    24 contributions of R$ 1.000, so the wealth curve ends at R$ 24.000
    less the fees paid: nothing performed, so nothing but the money is
    there. The split between holdings and cash is the whole-share
    remainder the strategy could not spend.
    """
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    _indicators(db_session, asset)

    result = run_backtest(
        db_session, [asset], _settings(costs=CostModel(exchange_rate=ZERO))
    )

    final = result.final
    assert final is not None
    assert final.contributed == Decimal(24000)
    assert final.total == Decimal(24000)
    assert final.holdings + final.cash == final.total
    assert result.trades.fees == ZERO


def test_the_contribution_line_grows_with_the_curve_rather_than_sitting_flat(
    db_session,
):
    """ADR-019's line: a total that grew on deposits must be readable as
    a total that grew on deposits.

    It starts at R$ 1.000 rather than at zero because the curve starts on
    the first session the portfolio exists at all, which is the day the
    first contribution landed.
    """
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    _indicators(db_session, asset)

    result = run_backtest(db_session, [asset], _settings())

    contributed = [point.contributed for point in result.wealth]
    assert contributed[0] == Decimal(1000)
    assert contributed == sorted(contributed)
    assert contributed[-1] == Decimal(24000)


def test_nothing_is_bought_until_the_statement_it_needs_had_been_filed(db_session):
    """Rule 109, end to end, and the reason a run starts quiet.

    The only indicators stored report the 2023 fiscal year, which the
    CVM's deadline makes public on 31 March 2024. Until then the asset
    covers 0,40 of the formula — Risk and Diversification, the two that
    need no statement — which is under the allocator's minimum, so it is
    skipped and the contribution sits as cash.

    A backtest without the lag would have been buying since January on a
    document that did not exist, and it would have looked like a strategy
    that works.
    """
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    _indicators(db_session, asset, year=2023)

    result = run_backtest(db_session, [asset], _settings())

    traded = [decision.day for decision in result.decisions if any(decision.orders)]
    assert traded
    assert min(traded) >= date(2024, 3, 31)

    quiet = [point for point in result.wealth if point.date < date(2024, 3, 31)]
    assert all(point.holdings == ZERO for point in quiet)
    assert all(point.cash == point.contributed for point in quiet)


def test_a_payout_is_credited_as_cash_and_reaches_the_next_contribution(db_session):
    """The dividend arrives in reais, not as an adjustment to the price."""
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    _indicators(db_session, asset)
    db_session.add(
        StoredAction(
            asset_id=asset.id,
            ex_date=date(2025, 3, 14),
            last_date_prior=date(2025, 3, 13),
            kind="CASH_DIVIDEND",
            cash_amount=Decimal("1.00"),
            label="DIVIDENDO",
            source="b3",
        )
    )
    db_session.commit()

    result = run_backtest(
        db_session, [asset], _settings(costs=CostModel(exchange_rate=ZERO))
    )

    assert result.trades.dividends_received > ZERO
    # The payout is money the investor did not contribute, so the final
    # total sits above the contribution line.
    assert result.final.total > result.final.contributed


def test_a_run_reports_the_costs_it_charged(db_session):
    """Rule 107: a backtest without costs is not a final result."""
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    _indicators(db_session, asset)

    result = run_backtest(db_session, [asset], _settings())

    assert result.trades.fees > ZERO
    assert result.settings.costs.exchange_rate == Decimal("0.0003")


def test_the_same_settings_produce_the_same_run(db_session):
    """Rule 113, over the whole I/O path and not only the pure engine."""
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    _indicators(db_session, asset)

    first = run_backtest(db_session, [asset], _settings())
    second = run_backtest(db_session, [asset], _settings())

    assert [(point.date, point.total) for point in first.wealth] == [
        (point.date, point.total) for point in second.wealth
    ]
    assert [(point.date, point.adjusted_close) for point in first.index] == [
        (point.date, point.adjusted_close) for point in second.index
    ]


def test_an_unknown_strategy_is_refused_rather_than_guessed_at(db_session):
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)

    with pytest.raises(ValueError, match="Unknown strategy"):
        run_backtest(db_session, [asset], _settings(strategy="whatever"))


def test_the_rebalancing_plan_is_a_strategy_the_engine_can_run(db_session):
    """The other order the roadmap asks for: gap first, not score first."""
    alpha = _asset(db_session, "AAA3")
    beta = _asset(db_session, "BBB3", sector="Financeiro")
    for asset in (alpha, beta):
        _prices(db_session, asset)
        _indicators(db_session, asset)

    result = run_backtest(
        db_session, [alpha, beta], _settings(strategy="rebalance-plan")
    )

    assert result.trades.buys > 0
    assert result.settings.strategy == "rebalance-plan"


def test_a_benchmark_is_only_measured_when_one_was_asked_for(db_session):
    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    _indicators(db_session, asset)

    without = run_backtest(db_session, [asset], _settings())
    assert without.comparison is None
    assert without.alpha is None

    with_index = run_backtest(db_session, [asset], _settings(), IBOVESPA)
    assert with_index.comparison is not None
    assert with_index.comparison.benchmark_code == IBOVESPA.code
    # Nothing was ingested for the Ibovespa, so its side is absent rather
    # than zero — and every figure that needs it is absent with it.
    assert with_index.comparison.benchmark.observations == 0
    assert with_index.alpha is None


def test_nothing_is_written_to_the_database(db_session):
    """Rule 16: a backtest is derived, like positions and plans."""
    from app.data.models.portfolio import Transaction

    asset = _asset(db_session, "AAA3")
    _prices(db_session, asset)
    _indicators(db_session, asset)

    run_backtest(db_session, [asset], _settings())

    assert db_session.query(Transaction).count() == 0
