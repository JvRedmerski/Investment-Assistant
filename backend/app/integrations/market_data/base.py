"""Market data provider abstraction (AGENTS.md rule 21).

The domain and API layers must depend only on these interfaces, never on
a concrete vendor SDK/HTTP client directly, so the underlying source can
change without the rest of the application knowing.

Three interfaces, because the sources answer different questions and no
source answers all of them. `DailyHistoryProvider` is the narrow one:
closed daily bars, which is all an open end-of-day archive such as B3's
COTAHIST can ever serve. `MarketDataProvider` adds the live quote, which
needs a vendor API. `CorporateEventProvider` is orthogonal to both — the
exchange's own file stamps the sessions on which a paper traded ex some
right, and a quote vendor does not.

Splitting them means no source has to pretend (see `cotahist.py`); each
implements only what it has, and a caller asks for the narrowest
interface that answers its question.
"""

from abc import ABC, abstractmethod
from datetime import date

from app.integrations.market_data.schemas import CorporateEvent, DailyBar, Quote


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

    #: Stamped onto every bar this source supplies, so a stored row says
    #: where it came from. That matters more now that two sources feed
    #: the same table and only one of them adjusts (ADR-023).
    source_name: str = "unknown"

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


class CorporateEventProvider(ABC):
    """A source that can say **when** an asset traded ex some right.

    Deliberately not folded into `DailyHistoryProvider`: a source of
    prices need not know anything about corporate actions, and the vendor
    that quotes them does not. Requiring every history source to answer
    this would force one of them to answer badly.

    What comes back is dates and kinds, never magnitudes — see
    `CorporateEvent` and ADR-023 on why the size of an event is a
    different problem with a different source.
    """

    @abstractmethod
    def get_corporate_events(
        self, ticker: str, start: date, end: date
    ) -> list[CorporateEvent]:
        """Every right `ticker` went ex within [start, end] (inclusive).

        Ordered by date. An asset that went through the window without a
        single distribution returns an empty list, which is a real answer
        and not an error.

        Raises:
            TickerNotFoundError: the provider has no data for this ticker.
            MarketDataUnavailableError: the provider could not be reached.
            InvalidMarketDataResponseError: the response could not be parsed.
        """
