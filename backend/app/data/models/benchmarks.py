from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.data.database import Base, utc_now

#: Precision for a benchmark observation.
#:
#: One column carries two very different magnitudes: the Ibovespa's level
#: (166,978.9375 points) and the CDI's daily rate as a fraction
#: (0.00043739). NUMERIC(24, 12) holds both exactly — 12 integer digits
#: for any index that has ever existed, and 12 decimal places, which is
#: four more than the six the SGS publishes a daily rate to.
#:
#: The decimals are the reason this is wider than the NUMERIC(18, 6) used
#: for money. A daily rate rounded to six places loses its last two
#: significant digits, and that error compounds 252 times a year into the
#: accumulated index every portfolio-versus-CDI comparison is built on.
BENCHMARK_VALUE = Numeric(24, 12)


class BenchmarkValue(Base):
    """One published observation of one benchmark series.

    Deliberately keyed by the benchmark's **code** rather than by a
    foreign key to a `benchmarks` table. The catalog of benchmarks lives
    in code (`app.domain.benchmarks.catalog`), not in a table, so there is
    no row to point at: adding a benchmark is a reviewed diff rather than
    a seed migration that two environments can disagree about.

    What the number in `value` *means* is therefore not stored here — it
    is the catalog's `kind` that says whether it is a level or a
    per-period rate. Reading a value without consulting the definition
    would eventually treat a CDI rate as if it were a price; every read
    path goes through `app.domain.benchmarks.series` for that reason.

    Values are stored exactly as the source published them, in the
    project's canonical unit (a fraction for a rate, a level for an
    index). No accumulated index is stored — see ADR-018 — because
    accumulation depends on the base date the caller asks about, and
    freezing one would answer a question nobody asked.
    """

    __tablename__ = "benchmark_values"
    __table_args__ = (
        # A single unique constraint, no separate index: PostgreSQL backs a
        # UNIQUE constraint with an index on the same columns, and adding
        # one explicitly is what left `assets.ticker` and `users.email`
        # with duplicated definitions that make `alembic check` report
        # drift (docs/memory/PROJECT_STATUS.md, Known Issue 17). Reads
        # filter on (benchmark_code, date range), which this serves.
        UniqueConstraint("benchmark_code", "date", name="uq_benchmark_value_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    benchmark_code: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(BENCHMARK_VALUE, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
