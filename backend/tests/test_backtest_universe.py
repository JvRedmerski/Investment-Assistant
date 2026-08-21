"""Tests for the strategy under test, and for the date it may read from
(W13-003).

Two questions here, and the second is the one rule 109 is about:

- Does the backtest run **this project's** allocator, over the portfolio
  the simulation actually built, rather than a reimplementation of it?
- Does it read a financial statement only from the day it was filed,
  rather than from the day the fiscal year happened to end?
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset, AssetPrice
from app.data.models.fundamentals import FinancialIndicator
from app.data.models.portfolio import Portfolio, Transaction, TransactionTypeEnum
from app.data.models.users import User
from app.domain.backtesting.availability import (
    PUBLICATION_LAG_MONTHS,
    available_from,
    latest_readable_period,
)
from app.domain.backtesting.simulation import (
    ContributionSchedule,
    SimulationState,
    simulate,
)
from app.domain.backtesting.universe import (
    contribution_strategy,
    exposure_from_positions,
    plan_on,
)
from app.domain.portfolio.service import compute_positions
from app.domain.recommendations.service import build_exposure, score_asset

ZERO = Decimal(0)


# -- when a statement became readable ---------------------------------


def test_the_default_lag_is_the_cvm_filing_deadline():
    """Three months, and named rather than inlined so a result can cite it."""
    assert PUBLICATION_LAG_MONTHS == 3


def test_a_fiscal_year_is_not_public_on_the_day_it_ends():
    assert available_from(date(2024, 12, 31)) == date(2025, 3, 31)


def test_the_lag_clamps_to_the_end_of_a_shorter_month():
    """30 November plus three months is 28 February, not 2 March."""
    assert available_from(date(2024, 11, 30)) == date(2025, 2, 28)
    assert available_from(date(2024, 11, 30), lag_months=15) == date(2026, 2, 28)


def test_the_clamp_knows_february_of_a_leap_year():
    assert available_from(date(2023, 11, 30), lag_months=3) == date(2024, 2, 29)


def test_the_readable_period_is_the_inverse_of_the_publication_date():
    assert latest_readable_period(date(2025, 3, 31)) == date(2024, 12, 31)


def test_a_statement_is_not_readable_the_day_before_it_is_filed():
    assert latest_readable_period(date(2025, 3, 30)) < date(2024, 12, 31)


def test_the_two_directions_only_ever_withhold_a_statement_longer():
    """A month-end shift can disagree by a day, never in the loose direction.

    31 March is filed by 30 June, and on 30 June the filter still says
    the newest readable period is 30 March — one day late. Late costs
    the backtest a little information; early would hand it information
    nobody had.
    """
    assert available_from(date(2025, 3, 31)) == date(2025, 6, 30)
    assert latest_readable_period(date(2025, 6, 30)) == date(2025, 3, 30)

    day = date(2020, 1, 1)
    while day < date(2030, 1, 1):
        readable = latest_readable_period(day)
        assert available_from(readable) <= day
        day += timedelta(days=1)


# -- the database side ------------------------------------------------


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
def assets(db_session):
    rows = [
        Asset(ticker="AAA3", name="Alpha", asset_type="STOCK", sector="Energia"),
        Asset(ticker="BBB3", name="Beta", asset_type="STOCK", sector="Financeiro"),
    ]
    db_session.add_all(rows)
    db_session.commit()
    for row in rows:
        db_session.refresh(row)
    return rows


def _add_indicator(db_session, asset, year, **overrides):
    """One year of indicators, good enough to clear the score floor."""
    values = {
        "roe": Decimal("0.20"),
        "roic": Decimal("0.15"),
        "net_margin": Decimal("0.20"),
        "pe": Decimal(5),
        "pb": Decimal("0.5"),
        "revenue_growth": Decimal("0.20"),
        "profit_growth": Decimal("0.20"),
    }
    values.update(overrides)
    db_session.add(
        FinancialIndicator(
            asset_id=asset.id, reference_date=date(year, 12, 31), **values
        )
    )
    db_session.commit()


def _add_prices(db_session, asset, first: date, days: int, close: str):
    price = Decimal(close)
    for offset in range(days):
        db_session.add(
            AssetPrice(
                asset_id=asset.id,
                date=first + timedelta(days=offset),
                open=price,
                high=price,
                low=price,
                close=price,
                adjusted_close=price,
                volume=1000,
            )
        )
    db_session.commit()


def _state(day: date, cash: str, transactions=(), closes=None) -> SimulationState:
    return SimulationState(
        day=day,
        cash=Decimal(cash),
        positions=compute_positions(list(transactions)),
        closes=closes or {},
    )


def _buy(asset_id: int, day: date, quantity: str, price: str, id_: int) -> Transaction:
    from datetime import UTC, datetime, time

    return Transaction(
        id=id_,
        portfolio_id=0,
        asset_id=asset_id,
        type=TransactionTypeEnum.BUY,
        quantity=Decimal(quantity),
        price=Decimal(price),
        fees=ZERO,
        transaction_date=datetime.combine(day, time.min, tzinfo=UTC),
    )


# -- rule 109, against the database -----------------------------------


def test_the_live_path_still_reads_a_statement_dated_on_or_before_the_day(
    db_session, assets
):
    """The lag defaults to zero, which leaves scoring exactly as it was."""
    alpha = assets[0]
    _add_indicator(db_session, alpha, 2023, roe=Decimal("0.05"))
    _add_indicator(db_session, alpha, 2024, roe=Decimal("0.20"))

    score = score_asset(
        db_session,
        alpha,
        build_exposure(db_session, _portfolio(db_session)),
        as_of=date(2025, 1, 2),
    )

    assert _quality_roe(score) == Decimal(100)


def test_a_backtest_cannot_read_a_year_that_had_not_been_filed_yet(db_session, assets):
    """2 January 2025 knows the 2023 statement, not the 2024 one."""
    alpha = assets[0]
    _add_indicator(db_session, alpha, 2023, roe=Decimal("0.05"))
    _add_indicator(db_session, alpha, 2024, roe=Decimal("0.20"))

    score = score_asset(
        db_session,
        alpha,
        build_exposure(db_session, _portfolio(db_session)),
        as_of=date(2025, 1, 2),
        publication_lag_months=PUBLICATION_LAG_MONTHS,
    )

    assert _quality_roe(score) == Decimal(25)


def test_the_same_backtest_reads_it_once_the_filing_deadline_has_passed(
    db_session, assets
):
    alpha = assets[0]
    _add_indicator(db_session, alpha, 2023, roe=Decimal("0.05"))
    _add_indicator(db_session, alpha, 2024, roe=Decimal("0.20"))

    score = score_asset(
        db_session,
        alpha,
        build_exposure(db_session, _portfolio(db_session)),
        as_of=date(2025, 3, 31),
        publication_lag_months=PUBLICATION_LAG_MONTHS,
    )

    assert _quality_roe(score) == Decimal(100)


def _quality_roe(score) -> Decimal:
    """The Quality pillar's ROE component, on the 0-100 scale."""
    quality = next(sub for sub in score.sub_scores if sub.name == "quality")
    return quality.components["roe"]


def _portfolio(db_session) -> Portfolio:
    """An empty portfolio, only so `build_exposure` has something to read."""
    existing = db_session.query(Portfolio).first()
    if existing is not None:
        return existing
    user = User(email="a@b.c", password_hash="x")
    db_session.add(user)
    db_session.commit()
    portfolio = Portfolio(user_id=user.id, name="Test")
    db_session.add(portfolio)
    db_session.commit()
    db_session.refresh(portfolio)
    return portfolio


# -- the exposure the simulated portfolio has -------------------------


def test_the_simulated_exposure_matches_what_the_live_engine_would_measure(
    db_session, assets
):
    """Same ledger, same weights — the backtest measures the live rule.

    Built two different ways on purpose: `build_exposure` from the
    database, `exposure_from_positions` from the simulation's in-memory
    positions. A divergence here would mean a backtest of a different
    concentration rule from the one the plan runs under.
    """
    alpha, beta = assets
    portfolio = _portfolio(db_session)
    stored = [
        _buy(alpha.id, date(2025, 1, 6), "100", "30", 1),
        _buy(beta.id, date(2025, 1, 6), "50", "20", 2),
    ]
    for transaction in stored:
        db_session.add(
            Transaction(
                portfolio_id=portfolio.id,
                asset_id=transaction.asset_id,
                type=transaction.type,
                quantity=transaction.quantity,
                price=transaction.price,
                fees=ZERO,
                transaction_date=transaction.transaction_date,
            )
        )
    db_session.commit()

    live = build_exposure(db_session, portfolio)
    simulated = exposure_from_positions(
        compute_positions(stored),
        {alpha.id: alpha.sector, beta.id: beta.sector},
    )

    assert simulated.total_invested == live.total_invested
    assert simulated.by_asset == live.by_asset
    assert simulated.by_sector == live.by_sector


def test_an_empty_portfolio_has_no_exposure_rather_than_a_zero_division():
    exposure = exposure_from_positions({}, {})

    assert exposure.total_invested == ZERO
    assert exposure.by_asset == {}


# -- the plan, on a past date -----------------------------------------


def test_the_plan_is_the_projects_own_allocator_run_on_a_past_date(db_session, assets):
    for asset in assets:
        _add_indicator(db_session, asset, 2023)
        _add_prices(db_session, asset, date(2024, 1, 1), 500, "30")

    plan = plan_on(
        db_session,
        assets,
        _state(date(2025, 1, 6), "1000"),
        contribution=Decimal(1000),
    )

    assert plan.contribution == Decimal(1000)
    assert {item.ticker for item in plan.allocations} == {"AAA3", "BBB3"}
    assert plan.allocated + plan.unallocated == plan.contribution


def test_the_plan_reads_the_portfolio_the_simulation_built_and_not_a_stored_one(
    db_session, assets
):
    """A simulated position at the ceiling is refused new money.

    The exposure comes from the state, so the Diversification pillar and
    the concentration ceilings see the portfolio the strategy actually
    accumulated up to that day.
    """
    alpha = assets[0]
    for asset in assets:
        _add_indicator(db_session, asset, 2023)
        _add_prices(db_session, asset, date(2024, 1, 1), 500, "30")

    held = [_buy(alpha.id, date(2024, 6, 3), "1000", "30", 1)]
    plan = plan_on(
        db_session,
        assets,
        _state(date(2025, 1, 6), "1000", transactions=held),
        contribution=Decimal(1000),
    )

    funded = {item.ticker for item in plan.allocations}
    assert funded == {"BBB3"}
    assert [item.reason.value for item in plan.skipped if item.ticker == "AAA3"] == [
        "ASSET_LIMIT_REACHED"
    ]


def test_a_price_printed_after_the_decision_cannot_change_it(db_session, assets):
    """Rule 58, through the whole plan rather than through one series.

    The second half of this test is what stops the first half being
    vacuous: the crash *would* have changed the answer — a plan made
    after it scores the asset lower — and the plan made before it is
    untouched, because the date cut the series off.
    """
    alpha = assets[0]
    for asset in assets:
        _add_indicator(db_session, asset, 2023)
        _add_prices(db_session, asset, date(2024, 1, 1), 500, "30")

    state = _state(date(2025, 1, 6), "1000")
    before = plan_on(db_session, assets, state, contribution=Decimal(1000))

    # A crash, printed after the decision. It cannot be known on the 6th.
    _add_prices(db_session, alpha, date(2025, 6, 1), 30, "1")

    unchanged = plan_on(db_session, assets, state, contribution=Decimal(1000))
    assert _lines(unchanged) == _lines(before)

    knowing = plan_on(
        db_session,
        assets,
        _state(date(2025, 7, 1), "1000"),
        contribution=Decimal(1000),
    )
    assert _score_of(knowing, "AAA3") < _score_of(before, "AAA3")


def _lines(plan) -> list[tuple[str, Decimal, Decimal]]:
    return [(item.ticker, item.amount, item.final_score) for item in plan.allocations]


def _score_of(plan, ticker: str) -> Decimal:
    return next(item.final_score for item in plan.allocations if item.ticker == ticker)


# -- the strategy the engine runs -------------------------------------


def test_the_strategy_offers_every_real_of_cash_and_not_just_the_month(
    db_session, assets
):
    """A remainder and a dividend are the same money as the contribution.

    Held back, they would make the backtest accumulate idle cash the real
    plan would have deployed. What reaches the allocator is the balance,
    so a larger balance produces a larger plan — capped, as always, by
    the concentration ceilings rather than by the money.
    """
    for asset in assets:
        _add_indicator(db_session, asset, 2023)
        _add_prices(db_session, asset, date(2024, 1, 1), 500, "30")

    strategy = contribution_strategy(db_session, assets)
    month_only = strategy(_state(date(2025, 1, 6), "1000"))
    with_remainder = strategy(_state(date(2025, 1, 6), "1500"))

    assert month_only and with_remainder
    assert sum(order.amount for order in with_remainder) <= Decimal(1500)
    assert sum(order.amount for order in with_remainder) > sum(
        order.amount for order in month_only
    )


def test_the_strategy_orders_nothing_without_cash(db_session, assets):
    strategy = contribution_strategy(db_session, assets)

    assert strategy(_state(date(2025, 1, 6), "0")) == []


def test_the_strategy_drives_the_engine_end_to_end(db_session, assets):
    """The two halves of the wave, connected: a real plan, really filled."""
    for asset in assets:
        _add_indicator(db_session, asset, 2023)
        _add_prices(db_session, asset, date(2024, 1, 1), 500, "30")

    closes = {
        asset.id: {
            date(2024, 1, 1) + timedelta(days=offset): Decimal(30)
            for offset in range(500)
        }
        for asset in assets
    }

    run = simulate(
        start=date(2025, 1, 1),
        end=date(2025, 3, 31),
        schedule=ContributionSchedule(amount=Decimal(1000), day_of_month=5),
        strategy=contribution_strategy(db_session, assets),
        closes=closes,
    )

    bought = [
        transaction
        for transaction in run.transactions
        if transaction.type is TransactionTypeEnum.BUY
    ]
    assert bought
    assert run.contributed == Decimal(3000)
    assert all(
        fill.quantity >= 0 for decision in run.decisions for fill in decision.fills
    )
