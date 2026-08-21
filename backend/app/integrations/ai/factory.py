"""Selects the configured `AIProvider` implementation.

Same pattern as the other three factories (AGENTS.md rules 21/40): the
rest of the application depends only on the abstract type, and this is
the single place that knows which concrete class backs
`settings.AI_PROVIDER`.

The one addition is `"none"`. Explanations are the only feature in this
project that can be switched off without changing a single number
elsewhere (ADR-009), so "no model at all" is a legitimate deployment
rather than a broken one — and it deserves to say so precisely instead
of failing as though the network were down.
"""

from app.core.config import settings
from app.integrations.ai.base import AIProvider
from app.integrations.ai.exceptions import AINotConfiguredError
from app.integrations.ai.gemini import GeminiProvider
from app.integrations.ai.ollama import OllamaProvider
from app.integrations.ai.schemas import Completion, CompletionRequest

#: Recorded as the model when explanations are switched off.
DISABLED_MODEL = "disabled"


class DisabledAIProvider(AIProvider):
    """The provider for a deployment that has deliberately no model.

    Refuses every call with `AINotConfiguredError`, which the API layer
    turns into a 503 naming the setting. Implemented as a provider
    rather than as a factory error so that "switched off" arrives
    through exactly the same path as "unreachable" and "no key" — one
    place in the route handles all three, and no caller has to know that
    building the provider can fail.
    """

    @property
    def model(self) -> str:
        return DISABLED_MODEL

    def complete(self, request: CompletionRequest) -> Completion:
        raise AINotConfiguredError(
            "Explanations are disabled: AI_PROVIDER is 'none'. Set it to "
            "'gemini' (with GEMINI_API_KEY) or to 'ollama'."
        )


def build_ai_provider() -> AIProvider:
    """The configured provider."""
    provider_name = settings.AI_PROVIDER.lower()

    if provider_name == "gemini":
        return GeminiProvider()
    if provider_name == "ollama":
        return OllamaProvider()
    if provider_name == "none":
        return DisabledAIProvider()
    raise ValueError(f"Unknown AI_PROVIDER: {settings.AI_PROVIDER!r}")
