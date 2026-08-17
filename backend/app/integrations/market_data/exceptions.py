class MarketDataError(Exception):
    """Base class for all market data integration failures."""


class TickerNotFoundError(MarketDataError):
    """The provider has no data for the requested ticker."""


class MarketDataUnavailableError(MarketDataError):
    """The provider could not be reached, or kept failing, after retries."""


class InvalidMarketDataResponseError(MarketDataError):
    """The provider responded, but its payload could not be parsed/validated."""
