"""Data transfer objects returned by a `BenchmarkProvider`.

Provider-agnostic, like `market_data.schemas`: nothing here knows about
the Banco Central's SGS API or about Brapi.

## The one distinction that shapes this whole package

A benchmark is published as one of two fundamentally different
quantities, and conflating them is the easiest way to produce a number
that looks right and is not:

- **`INDEX`** — a *level*, like the Ibovespa at 166,784 points. Two
  levels give a return by division, exactly like an asset price. It is
  already the shape `app.quant` consumes.

- **`RATE`** — a return *already realised* over the period the
  observation is dated with, like the CDI's 0.05166% for 2026-08-17.
  There is no level to divide: the number **is** the return. Treating a
  rate series as a price series would compute the change *of the rate*
  (0.052% to 0.0517% reads as a 0.9% "loss") instead of the return the
  rate represents. That is not a subtle error, it is a different
  quantity with a different sign.

`BenchmarkKind` therefore travels with every request and every stored
series, and `app.domain.benchmarks.series` is the single place that turns
a `RATE` series into something comparable with a price.

## Units

A provider always returns the project's canonical unit, converting from
whatever the source publishes:

- `RATE` values are **fractions**, never percents: `Decimal("0.0005166")`
  for the CDI's published `0.051660`. This matches `app.quant.returns`,
  where "returns are fractions, not percentages", so a stored rate can be
  compared against a computed return with no conversion in between —
  which is where a factor of 100 would otherwise hide.
- `INDEX` values are the level as published.

The provider converts because the provider is what knows its source's
unit; see `BcbSgsProvider`.
"""

import enum
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class BenchmarkKind(str, enum.Enum):
    """Whether a series publishes levels or per-period returns."""

    INDEX = "INDEX"
    RATE = "RATE"


class BenchmarkSource(str, enum.Enum):
    """Which integration serves a benchmark.

    Named here rather than as loose strings in the catalog so that the
    catalog (domain) and the factory (integrations) cannot drift apart
    over a typo: an unknown source becomes an import-time error instead
    of a runtime one.
    """

    #: Banco Central do Brasil, Sistema Gerenciador de Séries Temporais.
    BCB_SGS = "BCB_SGS"
    #: The configured market data provider, for indices quoted like a security.
    MARKET_DATA = "MARKET_DATA"


class BenchmarkObservation(BaseModel):
    """One published observation of a benchmark series.

    `value` is `None` when the source listed the date but reported no
    figure. It is deliberately not dropped by the provider and never
    filled in: passing the hole through lets `validate_benchmark_series`
    account for it in its report, the same contract `DailyBar` follows
    for a missing `adjusted_close` (ADR-016, AGENTS.md rule 44).
    """

    date: date
    value: Decimal | None
