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

⚠️ **NOT YET VERIFIED AGAINST A LIVE CALL.** The key in `.env` is valid
but the Gemini API is not enabled for its Google Cloud project, which
answers every request with HTTP 403 `SERVICE_DISABLED`. The parsing
below follows the published `v1beta` contract and must be treated as
unverified until one real call has been made and inspected — the
procedure in `docs/planning/IMPLEMENTATION_GUIDE.md`, and the lesson
that cost Wave 06 two silently-null fields. **No regression test is
written from these assumptions on purpose**: a mock built from a guess
does not check the guess, it reproduces it.

What *has* been observed live is the error envelope, because that is
what a disabled project returns:

    {"error": {"code": 403, "message": "Gemini API has not been used in
     project ... or it is disabled.", "status": "PERMISSION_DENIED"}}

Documented request shape (`POST /models/{model}:generateContent`):

    {"systemInstruction": {"parts": [{"text": ...}]},
     "contents": [{"role": "user", "parts": [{"text": ...}]}],
     "generationConfig": {"temperature": ..., "maxOutputTokens": ...}}

and the expected response:

    {"candidates": [{"content": {"parts": [{"text": ...}]},
                     "finishReason": "STOP"}],
     "usageMetadata": {"promptTokenCount": ..., "candidatesTokenCount": ...},
     "modelVersion": "..."}

Two documented cases return **no text at all** and are handled as
`AIResponseBlockedError` rather than as an empty completion: a prompt
refused up front (`promptFeedback.blockReason`), and a candidate that
stopped for a reason other than `STOP` with no parts to show for it —
which is also what a reasoning model does when the output budget is
spent before it writes anything.
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

#: `finishReason` values that mean the model completed normally.
_COMPLETE = frozenset({"STOP", "MAX_TOKENS"})


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
            raise AIResponseBlockedError(
                "Gemini returned no text "
                f"(finishReason={finish_reason or 'unspecified'})."
            )

        if finish_reason is not None and finish_reason not in _COMPLETE:
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
            output_tokens=_as_int(usage.get("candidatesTokenCount")),
        )


def _as_int(value: Any) -> int | None:
    """A token count, or `None` when the provider did not report one.

    Never a substituted zero, which would read as a request that cost
    nothing rather than one that was not measured.
    """
    return value if isinstance(value, int) else None
