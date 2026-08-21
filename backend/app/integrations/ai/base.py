"""AI provider abstraction (AGENTS.md rules 21 and 40).

The domain and API layers depend only on `AIProvider`, never on Gemini,
so the concrete model can be swapped — or switched off entirely —
without a single number changing anywhere in the system (ADR-009).

That last clause is the point of the seam, not a side effect. Every
other provider abstraction in this project hides a *source of data*;
this one hides a source of *prose*. Nothing downstream of it may feed a
score, a target weight, a plan, or an ordering (AGENTS.md rules 3 and
24), which is why the interface returns text and nothing that could be
mistaken for a computed value.
"""

from abc import ABC, abstractmethod

from app.integrations.ai.schemas import Completion, CompletionRequest


class AIProvider(ABC):
    """Abstract interface for a natural-language generation source."""

    @abstractmethod
    def complete(self, request: CompletionRequest) -> Completion:
        """Generate prose for `request`.

        Returns a `Completion` whose `text` is non-empty; a provider that
        received no usable text raises rather than fabricating one.

        Raises:
            AINotConfiguredError: the provider has no usable credential.
            AIUnavailableError: the provider could not be reached.
            InvalidAIResponseError: the response could not be parsed.
            AIResponseBlockedError: the provider returned no text on purpose.
        """

    @property
    @abstractmethod
    def model(self) -> str:
        """The model identifier this provider was configured to ask for.

        Requested, not resolved — the resolved one comes back on the
        `Completion`. Exposed so a caller can record what it asked for
        even when the call fails, which is the case where the two differ
        most usefully.
        """

    def close(self) -> None:
        """Release any transport held by the provider.

        Default no-op, matching `BenchmarkProvider`.
        """
