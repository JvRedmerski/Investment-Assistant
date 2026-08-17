"""Fundamentals provider abstraction (AGENTS.md rule 21).

Mirrors `app.integrations.market_data.base`: the domain and API layers
depend only on `FundamentalsProvider`, never on a concrete vendor, so
the underlying source can change without the rest of the application
knowing.

Scope note — **annual statements only**. The `fundamentals` table
identifies a row by `(asset_id, reference_date)` and has no column
distinguishing an annual filing from a quarterly one, so mixing both
would produce two rows that look identical but mean different things
(a fiscal year ending 2024-12-31 and its Q4 both report that same end
date). Quarterly ingestion is deliberately deferred until the schema
can tell them apart.
"""

from abc import ABC, abstractmethod

from app.integrations.fundamentals.schemas import FinancialStatement


class FundamentalsProvider(ABC):
    """Abstract interface for a financial statements source."""

    @abstractmethod
    def get_annual_statements(self, ticker: str) -> list[FinancialStatement]:
        """Fetch the available **annual** financial statements for `ticker`.

        Returns one entry per reported fiscal year. Line items the source
        does not report are `None`, never zero or a substitute value.

        Raises:
            FundamentalsNotFoundError: no fundamental data for this ticker.
            FundamentalsUnavailableError: the provider could not be reached.
            InvalidFundamentalsResponseError: the response could not be parsed.
        """

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by the provider."""
