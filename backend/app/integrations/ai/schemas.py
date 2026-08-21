"""Data transfer objects exchanged with an `AIProvider`.

Provider-agnostic, like `benchmarks.schemas` and `market_data.schemas`:
nothing here knows about Gemini's `generateContent` or about Ollama's
`/api/chat`.

## Why the interface is a single turn, and not a chat

Wave 12 exists to *explain numbers the backend already computed*
(AGENTS.md rule 3, ADR-009). That is a one-shot transformation: a fact
pack goes in, prose comes out. There is no conversation to keep, no
tool the model may call, and no state that survives the request — so
modelling a message history here would be inventing a capability the
product does not have and cannot audit.

Should a chat feature ever be wanted, it is a new method on the
interface, not a reinterpretation of this one.

## `text` is never empty

Both vendors can accept a request and deliberately return nothing: a
safety filter trips, or a model emits only whitespace. An empty
`Completion` would reach the user as an explanation box that explains
nothing, which is exactly the failure mode rule 44 forbids. Providers
therefore raise `AIResponseBlockedError` instead of constructing one,
and this model enforces it so no future provider can forget.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CompletionRequest(BaseModel):
    """One instruction plus one rendered prompt, ready to send.

    `system` carries the role and the guardrails; `user` carries the
    facts. They are separate fields rather than one concatenated string
    because the vendors keep them apart natively (Gemini's
    `systemInstruction`, Ollama's `system` role), and because it makes
    the boundary auditable: everything the model is allowed to treat as
    *data* is in exactly one place.
    """

    model_config = ConfigDict(frozen=True)

    system: str
    user: str
    #: Low by default, not zero. Text is exempt from the determinism rule
    #: (AGENTS.md rule 113) because it is not an input to any number, but
    #: an explanation that rewords itself on every refresh reads as
    #: unreliable, so variance is kept small deliberately.
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, gt=0)

    @field_validator("system", "user")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt segments must not be blank.")
        return value


class Completion(BaseModel):
    """What a provider produced for one `CompletionRequest`.

    `model` is the identifier the *provider reported*, not the one that
    was requested. Vendors resolve aliases server-side (`gemini-flash-latest`
    is a pointer), and an explanation is only auditable if the record
    says which model actually wrote it.

    Token counts are `None` when the provider does not report them —
    never zero, which would read as a request that cost nothing.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None

    @field_validator("text")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "Completion text is empty; providers must raise "
                "AIResponseBlockedError instead of returning one."
            )
        return value
