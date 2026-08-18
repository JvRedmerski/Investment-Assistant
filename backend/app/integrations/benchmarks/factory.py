"""Selects the `BenchmarkProvider` implementation a benchmark is served by.

Unlike `market_data.factory`, the choice is not a deployment setting: it
is a property of the benchmark itself. The CDI only exists at the Banco
Central and the Ibovespa only at a market data vendor, so the catalog
entry names the source and this factory is the one place that knows which
class backs it (AGENTS.md rules 21/40).
"""

from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.bcb import BcbSgsProvider
from app.integrations.benchmarks.brapi_index import BrapiIndexProvider
from app.integrations.benchmarks.schemas import BenchmarkSource


def build_benchmark_provider(source: BenchmarkSource) -> BenchmarkProvider:
    if source is BenchmarkSource.BCB_SGS:
        return BcbSgsProvider()
    if source is BenchmarkSource.MARKET_DATA:
        return BrapiIndexProvider()
    raise ValueError(f"Unknown benchmark source: {source!r}")
