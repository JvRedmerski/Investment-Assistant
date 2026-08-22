"""Producing one explanation: facts in, audited prose out.

The whole flow is four steps, and the order matters:

    fact pack → versioned prompt → provider → guard → Explanation

Nothing between the endpoint and the model may add a number, and nothing
after the model may remove one. The service's job is to keep that true
and to attach the evidence.

## The empty pack never reaches the model

If not one fact carries a value there is nothing to explain, and asking
a language model to explain nothing is precisely how it starts writing
plausible things. That case short-circuits into a fixed sentence and
spends no request — AGENTS.md rule 44's `Data unavailable.`, written in
the product's language because every other surface the investor reads is
in Portuguese and an English string here would be a worse answer, not a
more compliant one.
"""

import logging
from datetime import UTC, datetime

from app.domain.ai import guard
from app.domain.ai.prompting import build_request, prompt_version
from app.domain.ai.schemas import Explanation, FactPack
from app.integrations.ai.base import AIProvider

logger = logging.getLogger("investment_assistant.ai")

#: Recorded as the model when no request was made. Not an empty string:
#: "" would read as a missing record rather than as a deliberate absence.
NO_MODEL = "none"

#: What the investor is told when the backend computed nothing at all.
NO_DATA_TEXT = (
    "Dados indisponíveis. O sistema não conseguiu calcular nenhum dos "
    "números necessários para esta explicação, e nada foi estimado no "
    "lugar deles."
)


def explain(
    provider: AIProvider,
    pack: FactPack,
    *,
    temperature: float,
    max_output_tokens: int,
) -> Explanation:
    """Explain `pack` in natural language, with its evidence attached.

    Raises whatever the provider raises — `AINotConfiguredError`,
    `AIUnavailableError`, `InvalidAIResponseError`,
    `AIResponseBlockedError`. Deliberately not caught here: an
    explanation that failed to generate is not an explanation with an
    apology in it, and the API layer is where a failure becomes an HTTP
    status the client can act on.
    """
    version = prompt_version(pack.topic)

    if not pack.available:
        logger.info(
            "No computed facts for topic %s on %r; skipping the provider call.",
            pack.topic.value,
            pack.subject,
        )
        return Explanation(
            topic=pack.topic,
            subject=pack.subject,
            text=NO_DATA_TEXT,
            model=NO_MODEL,
            prompt_version=version,
            generated_at=datetime.now(UTC),
            facts=pack.facts,
            unverified_figures=(),
        )

    request = build_request(
        pack,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    completion = provider.complete(request)
    flagged = guard.unverified_figures(completion.text, pack.facts)

    if flagged:
        # Loud on purpose. A figure that traces to no fact is rule 44
        # being broken, and the fact that it is reported rather than
        # rejected (see `guard`) is not a reason for it to be quiet.
        logger.warning(
            "Model %s produced %d figure(s) absent from the fact pack for "
            "topic %s on %r: %s",
            completion.model,
            len(flagged),
            pack.topic.value,
            pack.subject,
            ", ".join(flagged),
        )

    if completion.truncated:
        # Same reasoning as the block above: an incomplete explanation
        # is not a quiet event. The operator fix is a setting
        # (`AI_MAX_OUTPUT_TOKENS`), and nobody changes a setting they
        # were never told about.
        logger.warning(
            "Model %s ran out of output budget explaining topic %s on %r; "
            "the text is truncated (prose=%s, reasoning=%s tokens).",
            completion.model,
            pack.topic.value,
            pack.subject,
            completion.output_tokens,
            completion.thinking_tokens,
        )

    return Explanation(
        topic=pack.topic,
        subject=pack.subject,
        text=completion.text,
        model=completion.model,
        prompt_version=version,
        generated_at=datetime.now(UTC),
        facts=pack.facts,
        unverified_figures=flagged,
        truncated=completion.truncated,
    )
