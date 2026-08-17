"""Market data provider abstraction (AGENTS.md rule 21).

The domain and API layers must depend only on `MarketDataProvider`, never
on a concrete vendor SDK/HTTP client directly, so the underlying source
(Brapi today, something else tomorrow) can change without the rest of the
application knowing. See `brapi.py` for the current implementation.
"""

from abc import ABC, abstractmethod
from datetime import date

from app.integrations.market_data.schemas import DailyBar, Quote


class MarketDataProvider(ABC):
    """Abstract interface for a market data source."""

    @abstractmethod
    def get_quote(self, ticker: str) -> Quote:
        """Fetch the latest available quote for `ticker`.

        Raises:
            TickerNotFoundError: the provider has no data for this ticker.
            MarketDataUnavailableError: the provider could not be reached.
            InvalidMarketDataResponseError: the response could not be parsed.
        """

    @abstractmethod
    def get_daily_history(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        """Fetch daily OHLCV bars for `ticker` within [start, end] (inclusive).

        Raises the same exceptions as `get_quote`.
        """
