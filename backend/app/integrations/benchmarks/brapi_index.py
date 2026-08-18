"""`BenchmarkProvider` for market indices quoted like a security, backed
by Brapi — the Ibovespa (`^BVSP`) today.

## Why this wraps `BrapiProvider` instead of parsing anything

Verified against the live API on 2026-08-18: Brapi returns `^BVSP` in
**exactly** the shape it returns a stock in — one `results[0]` entry with
a `historicalDataPrice[]` array of `date/open/high/low/close/volume/
adjustedClose`. There is no index-specific payload to parse.

So this class writes no parser. It delegates to the `MarketDataProvider`
already validated against four asset classes in Wave 06, and only maps
the resulting `DailyBar` onto the benchmark vocabulary. A second parser
for an identical payload would be the parallel implementation AGENTS.md
rule 8 forbids, and it would be the copy that rots.

What it does own is the **error vocabulary**: callers of the benchmark
package see `BenchmarkUnavailableError`, never `MarketDataUnavailableError`,
so a benchmark's backing source can change without a caller learning
about it.

## `adjusted_close`, on an index that has nothing to adjust

An index level carries no dividend or split adjustment, and the live
response confirms it: `adjustedClose` equalled `close` on all 19 bars
observed. The adjusted field is still the one read, so the value that
reaches `app.quant` comes from the same field for an index as for an
asset. When Brapi reports no adjusted close the hole is passed through
as `None` and rejected downstream, exactly as ADR-016 requires — never
back-filled from `close`.

## The live bar

The most recent entry of `historicalDataPrice` is the **session in
progress**, not a close. Two requests 2.5 minutes apart on 2026-08-18
returned 166851.5156 and then 166978.9375 for that same date. Since
ingestion never rewrites a stored date, storing that figure would freeze
an intraday snapshot as if it were a close. `validate_benchmark_series`
rejects it; see `INCOMPLETE_PERIOD` there.
"""

import logging
from datetime import date
from typing import Self

from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.exceptions import (
    BenchmarkSeriesNotFoundError,
    BenchmarkUnavailableError,
    InvalidBenchmarkResponseError,
)
from app.integrations.benchmarks.schemas import BenchmarkKind, BenchmarkObservation
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.factory import build_market_data_provider

logger = logging.getLogger("investment_assistant.benchmarks.brapi_index")


class BrapiIndexProvider(BenchmarkProvider):
    """Index levels sourced through the configured `MarketDataProvider`."""

    def __init__(self, market_data: MarketDataProvider | None = None) -> None:
        # Built through the market-data factory rather than by naming
        # `BrapiProvider`, so an index follows whatever provider the
        # deployment configured for prices.
        self._market_data = market_data or build_market_data_provider()

    def close(self) -> None:
        self._market_data.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_series(
        self,
        series_id: str,
        start: date,
        end: date,
        kind: BenchmarkKind,
    ) -> list[BenchmarkObservation]:
        if kind is not BenchmarkKind.INDEX:
            # A catalog mistake, not a runtime condition: this source
            # publishes levels and cannot invent a rate series.
            raise ValueError(
                f"{type(self).__name__} serves {BenchmarkKind.INDEX.value} "
                f"series only, not {kind.value}."
            )
        if start > end:
            raise ValueError("start date must not be after end date")

        try:
            bars = self._market_data.get_daily_history(series_id, start, end)
        except TickerNotFoundError as exc:
            raise BenchmarkSeriesNotFoundError(str(exc)) from exc
        except InvalidMarketDataResponseError as exc:
            raise InvalidBenchmarkResponseError(str(exc)) from exc
        except MarketDataUnavailableError as exc:
            raise BenchmarkUnavailableError(str(exc)) from exc

        observations = [
            BenchmarkObservation(date=bar.date, value=bar.adjusted_close)
            for bar in bars
        ]
        observations.sort(key=lambda observation: observation.date)
        return observations
