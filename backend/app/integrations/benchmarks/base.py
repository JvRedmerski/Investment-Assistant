"""Benchmark provider abstraction (AGENTS.md rule 21).

The domain and API layers depend only on `BenchmarkProvider`, never on a
concrete source, because the sources genuinely differ: the CDI and the
IPCA come from the Banco Central's open SGS API, and the Ibovespa from
Brapi. Which one backs a given benchmark is a catalog entry
(`app.domain.benchmarks.catalog`) resolved by `factory.py`, so adding a
benchmark does not touch a caller.
"""

from abc import ABC, abstractmethod
from datetime import date

from app.integrations.benchmarks.schemas import BenchmarkKind, BenchmarkObservation


class BenchmarkProvider(ABC):
    """Abstract interface for a source of benchmark series."""

    @abstractmethod
    def get_series(
        self,
        series_id: str,
        start: date,
        end: date,
        kind: BenchmarkKind,
    ) -> list[BenchmarkObservation]:
        """Fetch observations of `series_id` within [start, end] (inclusive).

        `series_id` is the identifier in the *provider's* own namespace —
        an SGS series number such as `"12"`, or a Brapi ticker such as
        `"^BVSP"`. `kind` tells the provider which canonical unit to
        return (see `schemas`); a provider that cannot serve a kind
        raises `ValueError`, since that is a catalog mistake rather than
        a runtime condition.

        Returns observations ordered oldest first. An empty list means
        the source has no observation in the window — a weekend for a
        daily series, say — which is not an error.

        Raises:
            BenchmarkSeriesNotFoundError: no such series at the provider.
            BenchmarkUnavailableError: the provider could not be reached.
            InvalidBenchmarkResponseError: the response could not be parsed.
        """

    def close(self) -> None:
        """Release any transport held by the provider.

        Default no-op so a provider without its own connection does not
        have to implement it.
        """
