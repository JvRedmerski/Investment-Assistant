"""Unit tests for sync_benchmark_series against a fake BenchmarkProvider
and a throwaway in-memory SQLite session (no FastAPI/HTTP layer)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.benchmarks import BenchmarkValue
from app.domain.benchmarks.catalog import CDI, IBOVESPA, IPCA
from app.domain.benchmarks.service import (
    read_benchmark_values,
    sync_benchmark_series,
)
from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.schemas import BenchmarkObservation

SETTLED = date(2030, 1, 1)


class FakeProvider(BenchmarkProvider):
    def __init__(self, observations=None, error=None):
        self._observations = observations or []
        self._error = error
        self.calls: list[tuple[str, date, date]] = []

    def get_series(self, series_id, start, end, kind):
        if self._error is not None:
            raise self._error
        self.calls.append((series_id, start, end))
        return [
            observation
            for observation in self._observations
            if start <= observation.date <= end
        ]


def _observation(day: int, value: str = "0.00043739") -> BenchmarkObservation:
    return BenchmarkObservation(date=date(2024, 1, day), value=Decimal(value))


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_sync_inserts_every_observation_when_nothing_is_stored(db_session):
    provider = FakeProvider([_observation(2), _observation(3), _observation(4)])

    result = sync_benchmark_series(
        db_session, provider, CDI, date(2024, 1, 1), date(2024, 1, 31), today=SETTLED
    )

    assert result.fetched == 3
    assert result.inserted == 3
    assert result.skipped_existing == 0
    assert result.rejected == 0
    assert db_session.query(BenchmarkValue).count() == 3


def test_the_stored_value_keeps_every_digit_the_source_published(db_session):
    """A daily rate rounded to six places loses two significant digits.

    Those digits compound 252 times a year into the accumulated index, so
    the column is NUMERIC(24, 12) rather than the NUMERIC(18, 6) used for
    money. This is the test that fails if that ever gets "simplified".
    """
    provider = FakeProvider([_observation(2, "0.000437390000")])

    sync_benchmark_series(
        db_session, provider, CDI, date(2024, 1, 1), date(2024, 1, 31), today=SETTLED
    )

    stored = db_session.query(BenchmarkValue).one()
    assert stored.value == Decimal("0.00043739")
    assert stored.benchmark_code == "CDI"
    assert stored.source == "BCB_SGS"


def test_a_second_sync_over_the_same_window_inserts_nothing(db_session):
    """Idempotence: the benchmark is the denominator of every comparison.

    If a rerun could rewrite an observation, a previously reported
    portfolio-versus-CDI figure would stop reproducing with nothing to
    show that the reference had moved rather than the portfolio.
    """
    observations = [_observation(2), _observation(3)]

    first = sync_benchmark_series(
        db_session,
        FakeProvider(observations),
        CDI,
        date(2024, 1, 1),
        date(2024, 1, 31),
        today=SETTLED,
    )
    second = sync_benchmark_series(
        db_session,
        FakeProvider(observations),
        CDI,
        date(2024, 1, 1),
        date(2024, 1, 31),
        today=SETTLED,
    )

    assert first.inserted == 2
    assert second.inserted == 0
    assert second.skipped_existing == 2
    assert db_session.query(BenchmarkValue).count() == 2


def test_a_changed_value_for_a_stored_date_is_never_written_over(db_session):
    """The Ibovespa's live bar returned three different closes in minutes.

    Whichever arrived first stays. That is the point: it can only be
    right to keep one if the one kept was settled when it was stored,
    which is what the incomplete-period rule guarantees.
    """
    sync_benchmark_series(
        db_session,
        FakeProvider([_observation(2, "0.00043739")]),
        CDI,
        date(2024, 1, 1),
        date(2024, 1, 31),
        today=SETTLED,
    )
    sync_benchmark_series(
        db_session,
        FakeProvider([_observation(2, "0.99999999")]),
        CDI,
        date(2024, 1, 1),
        date(2024, 1, 31),
        today=SETTLED,
    )

    assert db_session.query(BenchmarkValue).one().value == Decimal("0.00043739")


def test_a_later_sync_extends_the_series_without_touching_the_old_rows(db_session):
    sync_benchmark_series(
        db_session,
        FakeProvider([_observation(2), _observation(3)]),
        CDI,
        date(2024, 1, 1),
        date(2024, 1, 3),
        today=SETTLED,
    )
    result = sync_benchmark_series(
        db_session,
        FakeProvider([_observation(2), _observation(3), _observation(4)]),
        CDI,
        date(2024, 1, 1),
        date(2024, 1, 31),
        today=SETTLED,
    )

    assert result.inserted == 1
    assert result.skipped_existing == 2
    assert db_session.query(BenchmarkValue).count() == 3


def test_rejected_observations_are_counted_and_not_stored(db_session):
    provider = FakeProvider(
        [
            _observation(2),
            BenchmarkObservation(date=date(2024, 1, 3), value=None),
        ]
    )

    result = sync_benchmark_series(
        db_session, provider, CDI, date(2024, 1, 1), date(2024, 1, 31), today=SETTLED
    )

    assert result.fetched == 2
    assert result.inserted == 1
    assert result.rejected == 1
    assert db_session.query(BenchmarkValue).count() == 1


def test_the_period_in_progress_is_deferred_to_the_next_run(db_session):
    """One rejection on a daily sync is routine, and self-correcting."""
    live = BenchmarkObservation(date=date(2026, 8, 18), value=Decimal("166978.9375"))
    settled = BenchmarkObservation(date=date(2026, 8, 17), value=Decimal(166784))

    today_run = sync_benchmark_series(
        db_session,
        FakeProvider([settled, live]),
        IBOVESPA,
        date(2026, 8, 1),
        date(2026, 8, 18),
        today=date(2026, 8, 18),
    )
    # Next day, the source has published a settled close for the 18th.
    closed = BenchmarkObservation(date=date(2026, 8, 18), value=Decimal(166900))
    tomorrow_run = sync_benchmark_series(
        db_session,
        FakeProvider([settled, closed]),
        IBOVESPA,
        date(2026, 8, 1),
        date(2026, 8, 19),
        today=date(2026, 8, 19),
    )

    assert today_run.inserted == 1
    assert today_run.rejected == 1
    assert tomorrow_run.inserted == 1
    assert tomorrow_run.rejected == 0

    stored = read_benchmark_values(db_session, IBOVESPA)
    assert [value.date for value in stored] == [date(2026, 8, 17), date(2026, 8, 18)]
    assert stored[-1].value == Decimal(166900)


def test_two_benchmarks_do_not_collide_on_the_same_date(db_session):
    """`benchmark_code` is half the key, so CDI and Selic coexist."""
    sync_benchmark_series(
        db_session,
        FakeProvider([_observation(2, "0.00043739")]),
        CDI,
        date(2024, 1, 1),
        date(2024, 1, 31),
        today=SETTLED,
    )
    sync_benchmark_series(
        db_session,
        FakeProvider(
            [BenchmarkObservation(date=date(2024, 1, 1), value=Decimal("0.0042"))]
        ),
        IPCA,
        date(2024, 1, 1),
        date(2024, 1, 31),
        today=SETTLED,
    )

    assert db_session.query(BenchmarkValue).count() == 2
    assert len(read_benchmark_values(db_session, CDI)) == 1
    assert len(read_benchmark_values(db_session, IPCA)) == 1


def test_reads_come_back_oldest_first_and_honour_the_window(db_session):
    sync_benchmark_series(
        db_session,
        FakeProvider([_observation(4), _observation(2), _observation(3)]),
        CDI,
        date(2024, 1, 1),
        date(2024, 1, 31),
        today=SETTLED,
    )

    every = read_benchmark_values(db_session, CDI)
    windowed = read_benchmark_values(
        db_session, CDI, start=date(2024, 1, 3), end=date(2024, 1, 3)
    )

    assert [value.date for value in every] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
    ]
    assert [value.date for value in windowed] == [date(2024, 1, 3)]


def test_the_provider_is_asked_only_for_the_window_requested(db_session):
    provider = FakeProvider([_observation(2)])

    sync_benchmark_series(
        db_session, provider, CDI, date(2024, 1, 1), date(2024, 1, 31), today=SETTLED
    )

    assert provider.calls == [("12", date(2024, 1, 1), date(2024, 1, 31))]
