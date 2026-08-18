class BenchmarkError(Exception):
    """Base class for all benchmark integration failures."""


class BenchmarkSeriesNotFoundError(BenchmarkError):
    """The provider has no series under the requested identifier."""


class BenchmarkUnavailableError(BenchmarkError):
    """The provider could not be reached, or kept failing, after retries."""


class InvalidBenchmarkResponseError(BenchmarkError):
    """The provider responded, but its payload could not be parsed/validated."""
