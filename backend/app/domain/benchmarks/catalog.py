"""The benchmarks this project knows how to ingest.

A benchmark is defined in code, not in a database table, and the four
entries below are the whole configuration surface the roadmap's "outros
benchmarks configuráveis" asks for (docs/roadmap.md §20): adding one is a
row here, reviewed in a diff, with no seed migration and no way for two
environments to disagree about what "CDI" means.

Every field is a fact about the *source*, and every one of them has been
checked against a live response on 2026-08-18 — the series numbers most
of all, because a wrong SGS number does not fail loudly. Series 12 and 11
both return plausible daily percentages; only comparing them against the
published annualised series tells you which is which.

## Why the CDI's series is 12 and not 4389

The SGS publishes the CDI twice: series 12 as the **daily** rate
(`0.043739` for 2024-01-02) and series 4389 as the same rate **already
annualised** (`11.65` for the same day). We ingest series 12, the more
granular of the two, and derive the annual figure when a caller needs one
(`app.domain.benchmarks.series.annualised_rate`).

That direction is deliberate. Storing the annualised series would throw
away the daily compounding path — you cannot recover "how much did the
CDI actually yield between 3 and 17 January" from a series of annual
rates without assuming the rate held constant across the gap. The reverse
direction loses nothing, and it was verified to round-trip exactly:
compounding 0.043739% over 252 sessions gives 11.6499%, which is series
4389's 11.65 to the two decimals it publishes. The same check on
2026-08-17 gives 13.8998% against a published 13.90.

That is also the evidence for the base-252 convention used throughout —
see ADR-018.
"""

from dataclasses import dataclass

from app.integrations.benchmarks.schemas import BenchmarkKind, BenchmarkSource
from app.quant.returns import Periodicity


class UnknownBenchmarkError(KeyError):
    """No benchmark is registered under the requested code."""


@dataclass(frozen=True)
class BenchmarkDefinition:
    """Everything needed to fetch, store and interpret one benchmark.

    `periodicity` is the publication frequency, and it is load-bearing
    twice over: it decides how many observations make a year when a rate
    is annualised, and it decides when a period has finished and its
    observation may be stored (see `data_quality`).
    """

    code: str
    name: str
    kind: BenchmarkKind
    periodicity: Periodicity
    source: BenchmarkSource
    series_id: str
    description: str


CDI = BenchmarkDefinition(
    code="CDI",
    name="Certificado de Depósito Interbancário",
    kind=BenchmarkKind.RATE,
    periodicity=Periodicity.DAILY,
    source=BenchmarkSource.BCB_SGS,
    series_id="12",
    description=(
        "Daily interbank deposit rate published by the Banco Central "
        "(SGS series 12). The reference return for conservative Brazilian "
        "portfolios, and the risk-free rate for Sharpe and Sortino."
    ),
)

SELIC = BenchmarkDefinition(
    code="SELIC",
    name="Taxa Selic",
    kind=BenchmarkKind.RATE,
    periodicity=Periodicity.DAILY,
    source=BenchmarkSource.BCB_SGS,
    series_id="11",
    description=(
        "Daily Selic rate (SGS series 11). Tracks the CDI closely — the "
        "two were identical to six decimals on the dates sampled — and is "
        "the reference for Tesouro Selic."
    ),
)

IPCA = BenchmarkDefinition(
    code="IPCA",
    name="Índice Nacional de Preços ao Consumidor Amplo",
    kind=BenchmarkKind.RATE,
    periodicity=Periodicity.MONTHLY,
    source=BenchmarkSource.BCB_SGS,
    series_id="433",
    description=(
        "Monthly inflation (SGS series 433), dated on the first day of the "
        "month it measures. The benchmark that answers whether a portfolio "
        "gained purchasing power, not merely nominal value."
    ),
)

IBOVESPA = BenchmarkDefinition(
    code="IBOV",
    name="Índice Bovespa",
    kind=BenchmarkKind.INDEX,
    periodicity=Periodicity.DAILY,
    source=BenchmarkSource.MARKET_DATA,
    series_id="^BVSP",
    description=(
        "The B3 headline equity index, quoted in points. Served by the "
        "market data provider in the same payload shape as a stock, and "
        "used as the market series for beta."
    ),
)

#: Every benchmark, keyed by its public code.
BENCHMARKS: dict[str, BenchmarkDefinition] = {
    definition.code: definition for definition in (CDI, SELIC, IPCA, IBOVESPA)
}


def get_benchmark(code: str) -> BenchmarkDefinition:
    """The definition registered under `code`, case-insensitively.

    Raises `UnknownBenchmarkError` rather than returning `None`: an
    unregistered code is a caller mistake, not missing data, and the two
    should not be answered the same way (ADR-014 reserves `None` for "not
    computable from what we have").
    """
    try:
        return BENCHMARKS[code.strip().upper()]
    except KeyError as exc:
        known = ", ".join(sorted(BENCHMARKS))
        raise UnknownBenchmarkError(
            f"Unknown benchmark {code!r}. Known benchmarks: {known}."
        ) from exc


def list_benchmarks() -> list[BenchmarkDefinition]:
    """Every registered benchmark, ordered by code for a stable response."""
    return [BENCHMARKS[code] for code in sorted(BENCHMARKS)]
