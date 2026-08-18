from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from app.integrations.benchmarks.schemas import BenchmarkKind
from app.quant.returns import Periodicity


class BenchmarkResponse(BaseModel):
    """One entry of the benchmark catalog.

    `kind` is part of the contract, not decoration: a client that renders
    a `RATE` series as if it were an `INDEX` would plot the change *of the
    rate* instead of the return the rate represents.
    """

    code: str
    name: str
    kind: BenchmarkKind
    periodicity: Periodicity
    source: str
    series_id: str
    description: str


class BenchmarkSyncRequest(BaseModel):
    """Requested window to ingest from the benchmark's source.

    Both bounds are optional; the route supplies a default window when
    they are omitted. `start` cannot be after `end`.

    There is deliberately no upper bound on how far back `start` may
    reach: the SGS refuses windows wider than ten years, and the provider
    splits the request rather than making the caller do arithmetic.
    """

    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _validate_range(self) -> "BenchmarkSyncRequest":
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start date must not be after end date.")
        return self


class BenchmarkSyncResponse(BaseModel):
    """Result of ingesting a window of a benchmark series.

    `rejected` counting one on a daily sync is routine: it is normally
    the period still in progress, which the next run stores once the
    source publishes a settled figure.
    """

    code: str
    start: date
    end: date
    fetched: int
    inserted: int
    skipped_existing: int
    rejected: int


class BenchmarkValueResponse(BaseModel):
    """A single stored observation, read from the local store.

    Never triggers a call to the external source (AGENTS.md rule 23).
    `value` is in the project's canonical unit: a fraction for a `RATE`
    benchmark (`0.00043739`, not `0.043739`), a level for an `INDEX`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    benchmark_code: str
    date: date
    value: Decimal
    source: str
    created_at: datetime


class SeriesPerformanceResponse(BaseModel):
    """Standalone figures for one side of a comparison.

    `start_date`/`end_date` are the window actually measured, which is
    not always the window requested — a benchmark ingested later, or a
    monthly series whose latest print is not out yet. Reported so a
    comparison across two different windows is visible instead of silent
    (AGENTS.md rule 28).

    Returns are fractions: `0.15` is 15%. `max_drawdown` is negative by
    convention, and `0` there is a real measurement — the series never
    fell below a previous peak — while `null` means not enough data.
    """

    model_config = ConfigDict(from_attributes=True)

    start_date: date | None
    end_date: date | None
    observations: int
    periodicity: Periodicity
    total_return: Decimal | None
    annualised_return: Decimal | None
    volatility: Decimal | None
    max_drawdown: Decimal | None


class BenchmarkComparisonResponse(BaseModel):
    """A portfolio or asset set against one benchmark.

    - `excess_return` is a **difference** in fraction points: `0.03` is
      three percentage points above the benchmark.
    - `return_ratio` is a **multiple**: `1.15` is the "115% do CDI" a
      Brazilian investor expects. `null` unless **both** returns were
      strictly positive, which is the only case the idiom describes;
      outside it the ratio reads as the opposite of the truth, so
      `excess_return` is what to show.
    - `beta` is `null` for a rate benchmark by design — sensitivity to
      the CDI is not a quantity that means anything (see `comparison`).
    - `sharpe`/`sortino` are `null` when no CDI has been ingested for the
      window: computing them against an assumed zero rate would flatter
      every asset.

    Built with `model_validate` straight off the `BenchmarkComparison`
    dataclass, so the field names here and there must stay in step; a
    rename on one side fails loudly rather than dropping a field.
    """

    model_config = ConfigDict(from_attributes=True)

    benchmark_code: str
    benchmark_name: str
    subject: SeriesPerformanceResponse
    benchmark: SeriesPerformanceResponse
    excess_return: Decimal | None
    return_ratio: Decimal | None
    beta: Decimal | None
    sharpe: Decimal | None
    sortino: Decimal | None
    risk_free_rate: Decimal | None
