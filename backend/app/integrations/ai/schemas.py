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

    ## `truncated` is normalised here; `finish_reason` is not

    The two fields answer different questions and both are needed.
    `finish_reason` is the vendor's own string, kept raw for the audit
    trail — Gemini says `MAX_TOKENS`, Ollama says `length`, and a future
    provider will say a third thing. `truncated` is that same fact in
    the one vocabulary the domain can act on.

    The normalisation belongs to the provider module and nowhere else:
    it is the only layer allowed to know a vendor's spelling, and a
    domain that compared `finish_reason` against a set of vendor
    literals would break the first time a provider was added
    (AGENTS.md rule 22).

    ## Why a truncated completion is returned rather than raised

    It carries real text — usually a correct explanation that stops
    mid-sentence — and the caller can say so to the reader. Raising
    would discard a partly useful answer *and* spend one of the
    provider's metered calls to produce nothing, and the precedent is
    already set by `unverified_figures` (ADR-030): report, never
    silently reject.

    A truncation that leaves *no* text at all is a different case and
    still raises `AIResponseBlockedError` — there is nothing to report.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    #: Reasoning tokens, for the providers that both charge for them and
    #: report them separately. They are output the request paid for but
    #: that never reaches the reader, so folding them into
    #: `output_tokens` would misstate the answer's length while leaving
    #: them out entirely misstates its cost. Measured live on
    #: `gemini-3.7-flash`: 1.383 reasoning tokens against 295 of prose.
    thinking_tokens: int | None = None
    #: Whether the model stopped because it ran out of output budget
    #: rather than because it had finished saying what it had to say.
    truncated: bool = False

    @field_validator("text")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "Completion text is empty; providers must raise "
                "AIResponseBlockedError instead of returning one."
            )
        return value
