"""Market data provider abstraction (AGENTS.md rule 21).

The domain and API layers must depend only on these interfaces, never on
a concrete vendor SDK/HTTP client directly, so the underlying source can
change without the rest of the application knowing.

Two interfaces, because two sources answer different questions.
`DailyHistoryProvider` is the narrow one: closed daily bars, which is all
an open end-of-day archive such as B3's COTAHIST can ever serve.
`MarketDataProvider` adds the live quote, which needs a vendor API.
Splitting them means the historical archive does not have to pretend it
can quote (see `cotahist.py`); it implements only what it has.
"""

from abc import ABC, abstractmethod
from datetime import date

from app.integrations.market_data.schemas import DailyBar, Quote


class DailyHistoryProvider(ABC):
    """A source of closed daily OHLCV bars."""

    #: Whether this source publishes a corporate-action-adjusted close.
    #:
    #: This is a property of the *source*, not of a bar, and it changes
    #: what a missing `adjusted_close` means. For a vendor that does
    #: adjust (Brapi), `None` means "not published yet" — it arrives a
    #: session later, so the bar is rejected and picked up on the next
    #: sync (ADR-016). For a source that never adjusts (B3's COTAHIST,
    #: which prints the prices actually traded), `None` is permanent and
    #: rejecting would discard the entire series. `validate_daily_bars`
    #: reads this to tell the two apart.
    #:
    #: Defaults to `True`, so a provider that adjusts need not say so.
    reports_adjusted_close: bool = True

    @abstractmethod
    def get_daily_history(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        """Fetch daily OHLCV bars for `ticker` within [start, end] (inclusive).

        Raises:
            TickerNotFoundError: the provider has no data for this ticker.
            MarketDataUnavailableError: the provider could not be reached.
            InvalidMarketDataResponseError: the response could not be parsed.
            HistoryWindowTooLargeError: the window reaches further back than
                the provider (or the account's plan) will serve.
        """


class MarketDataProvider(DailyHistoryProvider, ABC):
    """A daily-history source that can also quote a live price."""

    @abstractmethod
    def get_quote(self, ticker: str) -> Quote:
        """Fetch the latest available quote for `ticker`.

        Raises:
            TickerNotFoundError: the provider has no data for this ticker.
            MarketDataUnavailableError: the provider could not be reached.
            InvalidMarketDataResponseError: the response could not be parsed.
        """
