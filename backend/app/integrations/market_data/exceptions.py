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


class IntradayNotAvailableError(MarketDataError):
    """The source will not serve intraday bars for this ticker.

    Its own error rather than `MarketDataUnavailableError`, because it
    is not an outage and no retry fixes it — and because the vendor's
    own message misnames the cause.

    Measured against the live free plan: `interval=15m` is served for
    PETR4, ITUB4, MGLU3 and VALE3 and refused for BBAS3 and BOVA11,
    every time, with HTTP 400 `INVALID_INTERVAL` and the text *"O
    intervalo '15m' não está disponível no seu plano"*. The interval is
    identical in both groups, so the interval is not what differs — the
    **ticker** is. BBAS3 answers HTTP 200 on the same endpoint at
    `interval=1d`, which rules out the ticker being unknown or delisted.

    One consequence is worth stating where it will be read: on the
    intraday path this refusal is returned *before* the ticker is
    resolved, so a ticker that genuinely does not exist also answers
    `INVALID_INTERVAL` rather than 404 (`NOSUCHTICKER99` does; the same
    ticker at `interval=1d` answers 404 `NOT_FOUND`). A caller therefore
    cannot read "no such ticker" out of this exception, and must not try.
    """
