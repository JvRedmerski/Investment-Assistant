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
