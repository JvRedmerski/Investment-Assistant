class MarketDataError(Exception):
    """Base class for all market data integration failures."""


class TickerNotFoundError(MarketDataError):
    """The provider has no data for the requested ticker."""


class MarketDataUnavailableError(MarketDataError):
    """The provider could not be reached, or kept failing, after retries."""


class InvalidMarketDataResponseError(MarketDataError):
    """The provider responded, but its payload could not be parsed/validated."""


class HistoryWindowTooLargeError(MarketDataError):
    """The requested window is longer than the provider plan can serve.

    Brapi exposes history as a fixed set of range buckets anchored at
    today, with no start-date parameter, and the free plan caps them at
    `3mo`. Asking for more used to send a request the caller already knew
    would be refused, surfacing as an opaque HTTP 400 several layers away
    from the cause. Raising here instead names the limit and points at the
    setting that lifts it on a paid plan.
    """
