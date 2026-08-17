class FundamentalsError(Exception):
    """Base class for all fundamentals integration failures."""


class FundamentalsNotFoundError(FundamentalsError):
    """The provider has no fundamental data for the requested ticker."""


class FundamentalsUnavailableError(FundamentalsError):
    """The provider could not be reached, or kept failing, after retries."""


class InvalidFundamentalsResponseError(FundamentalsError):
    """The provider responded, but its payload could not be parsed/validated."""
