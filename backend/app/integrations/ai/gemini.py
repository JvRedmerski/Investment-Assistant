"""`AIProvider` backed by Google's Gemini API (`generateContent`).

## Why REST and not the vendor SDK

`google-generativeai` was declared in `pyproject.toml` back in Wave 00
and never imported. Reaching Wave 12, three things argued against
picking it up, and the decision is recorded in
[ADR-029](../../../docs/decisions/ADR-029-ai-provider-speaks-rest.md):

- it is the SDK Google deprecated in favour of `google-genai`, so
  adopting it now means adopting a migration;
- it carries its own transport, retry policy and exception hierarchy,
  which would make this the only integration in the project that does
  not go through `RetryingJsonClient` and therefore the only one whose
  timeout, backoff and throttle behaviour is somebody else's (rule 22);
- the request this project makes is one POST with three fields.

So the dependency is dropped rather than used, and the wire format is
handled here, in the one module allowed to know it.

## What a live response actually looks like

✅ **Verified against live calls on 2026-08-22.** The documented
`v1beta` contract held name for name — `candidates[0].content.parts[]`,
`finishReason`, `usageMetadata.promptTokenCount`,
`usageMetadata.candidatesTokenCount` and `modelVersion` are all spelled
as published, unlike the Brapi episode in Wave 06 that this procedure
exists because of. The regression test in
`tests/test_gemini_provider.py` is built from captured payloads.

What the live calls *did* change is everything about the token budget,
because `gemini-flash-latest` resolves to **`gemini-3.7-flash`**, a
reasoning model:

- reasoning tokens are billed as output and reported separately, in
  `usageMetadata.thoughtsTokenCount`, which
  `usageMetadata.candidatesTokenCount` does **not** include. A measured
  call produced 1.383 reasoning tokens against 295 of prose, so reading
  `candidatesTokenCount` alone understates what the request cost by
  more than four times. Both are carried on `Completion`, never summed
  into one figure that would then answer neither question;
- reasoning is charged against `maxOutputTokens`, so the budget is
  shared with prose rather than reserved for it. Measured on a
  realistic 28-fact contribution-plan pack: at a budget of 1.024 the
  model spent **981** tokens thinking and returned a sentence cut after
  `"...entre três ativos:"`; the same pack at 2.048 finished normally
  with 1.383 + 295. Reasoning grows with the budget it is given, so the
  headroom has to be generous rather than exact — see
  `AI_MAX_OUTPUT_TOKENS`;
- consequently `MAX_TOKENS` is **truncation, not completion**. Treating
  it as a normal finish is what delivered that cut sentence to the
  reader as a finished explanation, and it happened at the default
  setting on an ordinary pack, not at some edge. It now sets
  `Completion.truncated`, and the decision to report rather than reject
  is [ADR-033](../../../docs/decisions/ADR-033-a-truncated-explanation-is-reported-not-discarded.md).

Two operational facts, also observed, that no code here can fix:
the key is on the free tier, capped at **20 requests per day** for this
model (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), and the
model returns HTTP 503 `"experiencing high demand"` often enough that
the shared retry policy earns its keep.

Documented request shape (`POST /models/{model}:generateContent`):

    {"systemInstruction": {"parts": [{"text": ...}]},
     "contents": [{"role": "user", "parts": [{"text": ...}]}],
     "generationConfig": {"temperature": ..., "maxOutputTokens": ...}}

and the response, as captured:

    {"candidates": [{"content": {"parts": [{"text": ..., "thoughtSignature": ...}],
                                 "role": "model"},
                     "finishReason": "STOP", "index": 0}],
     "usageMetadata": {"promptTokenCount": 180, "candidatesTokenCount": 153,
                       "thoughtsTokenCount": 548, "totalTokenCount": 881},
     "modelVersion": "gemini-3.7-flash",
     "responseId": "..."}

`thoughtSignature` rides alongside `text` inside a part and is ignored:
it is an opaque handle for multi-turn reasoning continuity, and this
interface is a single turn by design (`schemas.CompletionRequest`).

Three shapes return **no text at all**, and all three were observed
live rather than assumed. A prompt refused up front carries
`promptFeedback.blockReason`. A budget exhausted before the first word
comes back two different ways — `parts` holding a single part with no
`text` key, and `parts` missing altogether — and in that case
`candidatesTokenCount` is **absent**, not zero, which is why `_as_int`
must return `None` rather than substitute. All are
`AIResponseBlockedError`: an empty `Completion` is what rule 44 forbids.
"""

import logging
from typing import Any, Self

import httpx

from app.core.config import settings
from app.integrations.ai.base import AIProvider
from app.integrations.ai.exceptions import (
    AINotConfiguredError,
    AIResponseBlockedError,
    AIUnavailableError,
    InvalidAIResponseError,
)
from app.integrations.ai.schemas import Completion, CompletionRequest
from app.integrations.http import RetryingJsonClient

logger = logging.getLogger("investment_assistant.ai.gemini")

#: The header Google authenticates with. Deliberately a header and not
#: the `?key=` query parameter the quickstarts show: a key in a URL ends
#: up in access logs, proxy caches and error messages.
API_KEY_HEADER = "x-goog-api-key"

#: The one `finishReason` that means the model said everything it had
#: to say. `MAX_TOKENS` is deliberately **not** here: on a reasoning
#: model it means the budget ran out mid-sentence, which is a truncated
#: answer and not a complete one (ADR-033).
_COMPLETE = frozenset({"STOP"})

#: The `finishReason` that means the output budget ran out.
_TRUNCATED = "MAX_TOKENS"


class GeminiProvider(AIProvider):
    """`AIProvider` backed by Gemini's `generateContent` endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        min_request_interval: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self._model = model or settings.GEMINI_MODEL
        self._http = RetryingJsonClient(
            base_url=base_url or settings.GEMINI_BASE_URL,
            timeout=(timeout if timeout is not None else settings.AI_TIMEOUT_SECONDS),
            max_retries=(
                max_retries if max_retries is not None else settings.AI_MAX_RETRIES
            ),
            min_request_interval=(
                min_request_interval
                if min_request_interval is not None
                else settings.AI_MIN_REQUEST_INTERVAL_SECONDS
            ),
            not_found_error=AIUnavailableError,
            unavailable_error=AIUnavailableError,
            invalid_response_error=InvalidAIResponseError,
            logger=logger,
            default_headers=({API_KEY_HEADER: self._api_key} if self._api_key else {}),
            client=client,
        )

    @property
    def model(self) -> str:
        return self._model

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def complete(self, request: CompletionRequest) -> Completion:
        if not self._api_key:
            raise AINotConfiguredError(
                "GEMINI_API_KEY is empty. Set it, or set AI_PROVIDER to "
                "'ollama' or 'none'."
            )

        payload = {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "user", "parts": [{"text": request.user}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_output_tokens,
            },
        }
        document = self._http.post_json(
            f"/models/{self._model}:generateContent", payload
        )
        return self._parse(document)

    def _parse(self, document: Any) -> Completion:
        if not isinstance(document, dict):
            raise InvalidAIResponseError("Gemini response was not a JSON object.")

        blocked = (document.get("promptFeedback") or {}).get("blockReason")
        if blocked:
            raise AIResponseBlockedError(
                f"Gemini refused the prompt: blockReason={blocked}."
            )

        candidates = document.get("candidates") or []
        if not candidates:
            raise InvalidAIResponseError(
                "Gemini response carried no candidates and no blockReason."
            )

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason")
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(
            part["text"] for part in parts if isinstance(part.get("text"), str)
        )

        if not text.strip():
            # No text is a deliberate outcome here, not a malformed
            # payload: a safety stop, a recitation block, or an output
            # budget spent before the first word. Never an empty
            # Completion (rule 44).
            #
            # The budget case gets its own sentence because it is the
            # one an operator can actually act on, and "returned no
            # text" alone sends them looking at the prompt for a fault
            # that is in a setting.
            if finish_reason == _TRUNCATED:
                raise AIResponseBlockedError(
                    "Gemini spent the entire output budget on reasoning and "
                    "returned no text (finishReason=MAX_TOKENS). Raise "
                    "AI_MAX_OUTPUT_TOKENS: on a reasoning model the budget "
                    "is shared between reasoning and prose."
                )
            raise AIResponseBlockedError(
                "Gemini returned no text "
                f"(finishReason={finish_reason or 'unspecified'})."
            )

        truncated = finish_reason == _TRUNCATED
        if truncated:
            # Loud, and for the same reason `unverified_figures` is
            # loud: the reader is about to be shown a sentence that
            # stops mid-argument, and the fix is a setting nobody will
            # think to change unless the logs name it.
            logger.warning(
                "Gemini truncated the answer at the output budget "
                "(prompt=%s, reasoning=%s, prose=%s tokens). Raise "
                "AI_MAX_OUTPUT_TOKENS.",
                usage_of(document, "promptTokenCount"),
                usage_of(document, "thoughtsTokenCount"),
                usage_of(document, "candidatesTokenCount"),
            )
        elif finish_reason is not None and finish_reason not in _COMPLETE:
            logger.warning(
                "Gemini returned text with an unusual finishReason: %s",
                finish_reason,
            )

        usage = document.get("usageMetadata") or {}
        return Completion(
            text=text,
            # The resolved model, when the API reports it: an alias such
            # as `gemini-flash-latest` is a pointer, and the audit trail
            # needs what actually answered.
            model=document.get("modelVersion") or self._model,
            finish_reason=finish_reason,
            prompt_tokens=_as_int(usage.get("promptTokenCount")),
            # Prose only. The reasoning the request also paid for is a
            # separate figure, because summing them would report an
            # answer four times longer than the one the reader got.
            output_tokens=_as_int(usage.get("candidatesTokenCount")),
            thinking_tokens=_as_int(usage.get("thoughtsTokenCount")),
            truncated=truncated,
        )


def usage_of(document: Any, field: str) -> int | None:
    """One `usageMetadata` count, for the log line that reports a
    truncation. Tolerates a malformed envelope because a logging call is
    the worst possible place to raise."""
    if not isinstance(document, dict):
        return None
    return _as_int((document.get("usageMetadata") or {}).get(field))


def _as_int(value: Any) -> int | None:
    """A token count, or `None` when the provider did not report one.

    Never a substituted zero, which would read as a request that cost
    nothing rather than one that was not measured.
    """
    return value if isinstance(value, int) else None
