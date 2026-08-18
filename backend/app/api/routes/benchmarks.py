from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_benchmark_provider, get_current_user
from app.data.database import get_db
from app.data.models.benchmarks import BenchmarkValue
from app.data.models.users import User
from app.domain.benchmarks.catalog import (
    BenchmarkDefinition,
    UnknownBenchmarkError,
    get_benchmark,
    list_benchmarks,
)
from app.domain.benchmarks.schemas import (
    BenchmarkResponse,
    BenchmarkSyncRequest,
    BenchmarkSyncResponse,
    BenchmarkValueResponse,
)
from app.domain.benchmarks.service import read_benchmark_values, sync_benchmark_series
from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.exceptions import (
    BenchmarkSeriesNotFoundError,
    BenchmarkUnavailableError,
    InvalidBenchmarkResponseError,
)

router = APIRouter(prefix="/benchmarks", tags=["Benchmarks"])

#: Default window a sync covers when the caller gives no bounds.
#:
#: A year rather than the 30 days used for prices: a benchmark is
#: ingested to be compared against, and a comparison over one month of
#: daily observations is too short for any of the risk metrics to mean
#: much. One year is also comfortably inside the SGS ten-year limit, so
#: the common case stays a single request.
_DEFAULT_SYNC_WINDOW_DAYS = 365


def _definition_or_404(code: str) -> BenchmarkDefinition:
    try:
        return get_benchmark(code)
    except UnknownBenchmarkError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "BENCHMARK_NOT_FOUND",
                    "message": f"Unknown benchmark {code}.",
                }
            },
        ) from exc


@router.get("", response_model=list[BenchmarkResponse])
def list_available_benchmarks(
    current_user: User = Depends(get_current_user),
) -> list[BenchmarkResponse]:
    """The benchmarks this deployment can ingest and compare against.

    Served from the code catalog, so it never touches the database or an
    external source.
    """
    return [
        BenchmarkResponse(
            code=definition.code,
            name=definition.name,
            kind=definition.kind,
            periodicity=definition.periodicity,
            source=definition.source.value,
            series_id=definition.series_id,
            description=definition.description,
        )
        for definition in list_benchmarks()
    ]


@router.post("/{code}/sync", response_model=BenchmarkSyncResponse)
def sync_benchmark(
    code: str,
    payload: BenchmarkSyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: BenchmarkProvider = Depends(get_benchmark_provider),
) -> BenchmarkSyncResponse:
    """Fetch a window of the benchmark's series from its source and store it.

    The only endpoint that calls an external source for benchmarks;
    reading (`GET /{code}/values`) always comes from the database
    (AGENTS.md rule 23).
    """
    definition = _definition_or_404(code)

    # Explicit UTC "today" (AGENTS.md rule 18 — never assume a timezone
    # implicitly), matching how price sync bounds its window.
    today = datetime.now(UTC).date()
    end = payload.end or today
    start = payload.start or (end - timedelta(days=_DEFAULT_SYNC_WINDOW_DAYS))

    try:
        result = sync_benchmark_series(
            db, provider, definition, start, end, today=today
        )
    except BenchmarkSeriesNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "BENCHMARK_SERIES_NOT_FOUND",
                    "message": (
                        f"Source {definition.source.value} has no series "
                        f"{definition.series_id} for {definition.code}."
                    ),
                }
            },
        ) from exc
    except BenchmarkUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "BENCHMARK_SOURCE_UNAVAILABLE",
                    "message": (
                        f"Source {definition.source.value} is currently "
                        f"unavailable."
                    ),
                }
            },
        ) from exc
    except InvalidBenchmarkResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "BENCHMARK_INVALID_RESPONSE",
                    "message": (
                        f"Source {definition.source.value} returned an "
                        f"unparseable response."
                    ),
                }
            },
        ) from exc

    return BenchmarkSyncResponse(
        code=result.code,
        start=result.start,
        end=result.end,
        fetched=result.fetched,
        inserted=result.inserted,
        skipped_existing=result.skipped_existing,
        rejected=result.rejected,
    )


@router.get("/{code}/values", response_model=list[BenchmarkValueResponse])
def list_benchmark_values(
    code: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BenchmarkValue]:
    """Read stored observations of a benchmark, oldest first.

    Never queries the external source (AGENTS.md rule 23) — run
    `POST /{code}/sync` first. Values come back in the canonical unit: a
    fraction for a `RATE` benchmark, a level for an `INDEX`.
    """
    definition = _definition_or_404(code)
    return read_benchmark_values(db, definition, start, end)
