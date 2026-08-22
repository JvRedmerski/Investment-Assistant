"""Tests for the walk-forward service (W14-003).

Against a throwaway session, like the backtest service it composes: no
provider is involved, because a replay reads stored data and nothing else
(rule 23).

What is exercised here is the discipline, not the arithmetic. `quant`
owns the figures and `run_backtest` owns the replay; what can only be
tested at this level is that the choice is made on train and validation,
that nothing measured on test ever reaches a selection, and that a fold
which cannot choose says so instead of choosing anyway.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset, AssetPrice
from app.data.models.benchmarks import BenchmarkValue
from app.data.models.fundamentals import FinancialIndicator
from app.domain.backtesting.folds import WINDOW_TOO_SHORT, WalkForwardScheme
from app.domain.backtesting.grid import BASELINE, WALK_FORWARD_GRID_VERSION
from app.domain.backtesting.objectives import (
    OBJECTIVE_UNAVAILABLE,
    SelectionObjective,
)
from app.domain.backtesting.service import NO_TOTAL_RETURN_SERIES
from app.domain.backtesting.walkforward import (
    NOTHING_TESTABLE,
    SINGLE_FOLD,
    WalkForwardSettings,
    run_walk_forward,
)
from app.domain.benchmarks.catalog import CDI

FIRST = date(2024, 1, 1)
QUARTERLY = WalkForwardScheme(segment_months=3, step_months=3)

#: Nine months from `FIRST`: exactly one quarterly fold.
ONE_FOLD_END = date(2024, 9, 30)
#: Twelve months: two quarterly folds, the second training on what the
#: first validated.
TWO_FOLD_END = date(2024, 12, 31)


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


def _indicators(db_session, asset: Asset, year: int = 2022) -> None:
    """A filing old enough to be public throughout the tested window.

    The CVM lag (ADR-031) is three months, so a 2022 year-end is readable
    from April 2023 — before any segment here opens.
    """
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
    days: int = 400,
    adjusted_from: date | None = FIRST,
    drift: str = "0",
) -> None:
    """A series that drifts by `drift` reais a session, adjusted or not."""
    price = Decimal(close)
    step = Decimal(drift)
    for offset in range(days):
        day = first + timedelta(days=offset)
        value = price + step * offset
        db_session.add(
            AssetPrice(
                asset_id=asset.id,
                date=day,
                open=value,
                high=value,
                low=value,
                close=value,
                adjusted_close=(
                    value
                    if adjusted_from is not None and day >= adjusted_from
                    else None
                ),
                volume=1000,
            )
        )
    db_session.commit()


def _cdi(db_session, days: int = 400, first: date = FIRST) -> None:
    for offset in range(days):
        db_session.add(
            BenchmarkValue(
                benchmark_code=CDI.code,
                date=first + timedelta(days=offset),
                value=Decimal("0.0005"),
                source="bcb",
            )
        )
    db_session.commit()


def _settings(**overrides) -> WalkForwardSettings:
    values = {
        "start": FIRST,
        "end": ONE_FOLD_END,
        "strategy": "contribution-plan",
        "contribution": Decimal(1000),
        "day_of_month": 5,
        "scheme": QUARTERLY,
        "objective": SelectionObjective.TOTAL_RETURN,
    }
    values.update(overrides)
    return WalkForwardSettings(**values)


@pytest.fixture
def universe(db_session):
    """Two assets with statements, prices and a total-return series."""
    assets = []
    for ticker, drift in (("AAA3", "0.01"), ("BBB3", "0.02")):
        asset = _asset(db_session, ticker, sector=ticker)
        _prices(db_session, asset, drift=drift)
        _indicators(db_session, asset)
        assets.append(asset)
    return assets


# -- the shape of a run -----------------------------------------------


def test_the_folds_are_laid_over_the_replayable_window(db_session, universe):
    result = run_walk_forward(db_session, universe, _settings())

    assert result.window.start == FIRST
    assert result.window.end == ONE_FOLD_END
    assert result.partition.refusal is None
    assert len(result.folds) == 1
    assert result.folds[0].train.start == result.window.start
    assert result.folds[0].test.end == result.window.end


def test_the_window_never_runs_past_the_last_stored_session(db_session, universe):
    """Prices stop in early 2025; a request to 2026 does not invent folds."""
    result = run_walk_forward(db_session, universe, _settings(end=date(2026, 12, 31)))

    assert result.window.requested_end == date(2026, 12, 31)
    assert result.window.end == FIRST + timedelta(days=399)


def test_a_late_total_return_series_moves_the_window_and_names_the_asset(
    db_session, universe
):
    late = _asset(db_session, "CCC3", sector="Financeiro")
    _prices(db_session, late, adjusted_from=date(2024, 4, 1))
    _indicators(db_session, late)

    result = run_walk_forward(
        db_session, [*universe, late], _settings(end=TWO_FOLD_END)
    )

    assert result.window.start == date(2024, 4, 1)
    assert result.window.bounded_by == "CCC3"
    assert result.folds[0].train.start == date(2024, 4, 1)


def test_an_asset_with_no_adjusted_series_is_excluded_by_name(db_session, universe):
    unusable = _asset(db_session, "DDD3", sector="Varejo")
    _prices(db_session, unusable, adjusted_from=None)

    result = run_walk_forward(db_session, [*universe, unusable], _settings())

    assert ("DDD3", NO_TOTAL_RETURN_SERIES) in result.excluded
    assert "DDD3" not in result.universe


def test_the_grid_and_its_version_travel_with_the_result(db_session, universe):
    result = run_walk_forward(db_session, universe, _settings())

    assert result.grid_version == WALK_FORWARD_GRID_VERSION
    assert len(result.candidates) == 7
    assert result.candidates[0].name == BASELINE


# -- train chooses, validation confirms, test only reports ------------


def test_every_candidate_is_trained_and_only_the_shortlist_validated(
    db_session, universe
):
    result = run_walk_forward(db_session, universe, _settings())
    fold = result.folds[0]

    assert len(fold.trained) == len(result.candidates)
    assert len(fold.shortlist) <= result.settings.shortlist
    assert [run.name for run in fold.validated] == list(fold.shortlist)


def test_the_winner_is_the_best_of_the_validation_ranking(db_session, universe):
    fold = run_walk_forward(db_session, universe, _settings()).folds[0]

    scored = [run for run in fold.validated if run.outcome.objective is not None]
    best = max(run.outcome.objective for run in scored)

    assert fold.selected in fold.shortlist
    assert fold.in_sample == best


def test_nothing_measured_on_test_ever_reaches_a_selection(db_session, universe):
    """Rule 61, stated as the property that makes the figure mean anything."""
    fold = run_walk_forward(db_session, universe, _settings()).folds[0]

    assert fold.test.start > fold.validation.end
    assert fold.tested is not None
    # The winner was fixed by the validation ranking alone: the test
    # segment produced exactly one run, of that candidate.
    assert (
        fold.selected
        == max(
            (run for run in fold.validated if run.outcome.objective is not None),
            key=lambda run: run.outcome.objective,
        ).name
    )


def test_degradation_is_the_in_sample_figure_less_the_out_of_sample_one(
    db_session, universe
):
    fold = run_walk_forward(db_session, universe, _settings()).folds[0]

    assert fold.degradation == fold.in_sample - fold.out_of_sample
    assert fold.out_of_sample == fold.tested.objective


def test_a_dead_heat_goes_to_the_policy_already_in_production(db_session):
    """Flat prices make every candidate identical; the baseline keeps it."""
    for ticker in ("AAA3", "BBB3"):
        asset = _asset(db_session, ticker, sector=ticker)
        _prices(db_session, asset, drift="0")
        _indicators(db_session, asset)
    assets = list(db_session.query(Asset).order_by(Asset.ticker))

    fold = run_walk_forward(db_session, assets, _settings()).folds[0]

    assert fold.selected == BASELINE


# -- refusing rather than inventing -----------------------------------


def test_a_window_too_short_produces_no_folds_and_says_why(db_session, universe):
    result = run_walk_forward(db_session, universe, _settings(end=date(2024, 5, 31)))

    assert result.folds == ()
    assert result.partition.refusal == WINDOW_TOO_SHORT
    assert result.stability.refusal == WINDOW_TOO_SHORT
    assert result.stability.out_of_sample_mean is None


def test_an_unscorable_objective_leaves_the_fold_without_a_winner(db_session, universe):
    """Sharpe needs the CDI, and no CDI has been ingested here."""
    result = run_walk_forward(
        db_session, universe, _settings(objective=SelectionObjective.SHARPE)
    )
    fold = result.folds[0]

    assert fold.selected is None
    assert fold.tested is None
    assert fold.refusal == OBJECTIVE_UNAVAILABLE
    assert result.stability.refusal == OBJECTIVE_UNAVAILABLE
    # The runs still happened and are still reported — the fold could not
    # choose, which is not the same as the fold not running.
    assert len(fold.trained) == len(result.candidates)


def test_the_same_run_selects_on_sharpe_once_the_cdi_exists(db_session, universe):
    _cdi(db_session)

    fold = run_walk_forward(
        db_session, universe, _settings(objective=SelectionObjective.SHARPE)
    ).folds[0]

    assert fold.selected is not None
    assert fold.refusal is None
    assert fold.tested.metrics.sharpe is not None


def test_nothing_testable_is_named_rather_than_returned_as_zero(db_session):
    empty = _asset(db_session, "EEE3")

    result = run_walk_forward(db_session, [empty], _settings())

    assert result.universe == ()
    assert result.folds == ()
    assert result.stability.refusal == NOTHING_TESTABLE
    assert result.partition.refusal == NOTHING_TESTABLE


# -- stability across folds -------------------------------------------


def test_one_fold_is_not_a_sample(db_session, universe):
    """A spread of zero over one observation would read as perfect stability."""
    stability = run_walk_forward(db_session, universe, _settings()).stability

    assert stability.folds == 1
    assert stability.measured_folds == 1
    assert stability.refusal == SINGLE_FOLD
    assert stability.out_of_sample_mean is None
    assert stability.out_of_sample_stdev is None
    assert stability.selection_rate is None
    # The winner of the single fold is still reported — it is a fact
    # about that fold, and only the aggregate is withheld.
    assert stability.most_selected is not None


def test_two_folds_are_aggregated_and_the_repetition_is_reported(db_session, universe):
    result = run_walk_forward(db_session, universe, _settings(end=TWO_FOLD_END))
    stability = result.stability

    assert len(result.folds) == 2
    assert stability.refusal is None
    assert stability.measured_folds == 2
    assert stability.out_of_sample_mean is not None
    assert stability.out_of_sample_min <= stability.out_of_sample_mean
    assert stability.out_of_sample_mean <= stability.out_of_sample_max
    assert stability.out_of_sample_stdev is not None
    assert sum(stability.selections.values()) == 2
    assert stability.selection_rate == Decimal(
        stability.selections[stability.most_selected]
    ) / Decimal(2)


def test_positive_folds_counts_the_out_of_sample_wins(db_session, universe):
    result = run_walk_forward(db_session, universe, _settings(end=TWO_FOLD_END))

    expected = sum(1 for fold in result.folds if (fold.out_of_sample or Decimal(0)) > 0)
    assert result.stability.positive_folds == expected


# -- determinism (rule 113) -------------------------------------------


def test_the_same_settings_produce_the_same_walk_forward(db_session, universe):
    first = run_walk_forward(db_session, universe, _settings(end=TWO_FOLD_END))
    second = run_walk_forward(db_session, universe, _settings(end=TWO_FOLD_END))

    assert [fold.selected for fold in first.folds] == [
        fold.selected for fold in second.folds
    ]
    assert [fold.out_of_sample for fold in first.folds] == [
        fold.out_of_sample for fold in second.folds
    ]
    assert first.stability == second.stability
