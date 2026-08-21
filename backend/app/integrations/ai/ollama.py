"""`AIProvider` backed by a local Ollama server (`POST /api/chat`).

AGENTS.md rule 42 asks that the architecture not depend exclusively on a
proprietary API. This is the implementation of that clause: same
interface, same call sites, no key, no quota, and nothing leaving the
machine — which also makes it the right choice for anyone uncomfortable
sending portfolio figures to a hosted model (rule 91).

## What a live response actually looks like

⚠️ **NOT YET VERIFIED AGAINST A LIVE SERVER.** No Ollama is installed on
this machine, so the parsing below follows the published API and is
unverified, exactly like `gemini.py`. **No regression test is written
from these assumptions**, for the reason recorded in
`docs/planning/IMPLEMENTATION_GUIDE.md`: a mock built from a guess
reproduces the guess instead of checking it.

Documented request shape:

    {"model": "llama3.2",
     "messages": [{"role": "system", "content": ...},
                  {"role": "user", "content": ...}],
     "stream": false,
     "options": {"temperature": ..., "num_predict": ...}}

and response:

    {"model": "llama3.2", "message": {"role": "assistant", "content": ...},
     "done": true, "done_reason": "stop",
     "prompt_eval_count": ..., "eval_count": ...}

`stream` is explicitly false. Left at its default the server answers
with a sequence of newline-delimited JSON objects, which is not a JSON
document and would fail parsing in `RetryingJsonClient` — one of those
defaults that is fine for a chat UI and wrong for everything else.
"""

import logging
from typing import Any, Self

import httpx

from app.core.config import settings
from app.integrations.ai.base import AIProvider
from app.integrations.ai.exceptions import (
    AIResponseBlockedError,
    AIUnavailableError,
    InvalidAIResponseError,
)
from app.integrations.ai.schemas import Completion, CompletionRequest
from app.integrations.http import RetryingJsonClient

logger = logging.getLogger("investment_assistant.ai.ollama")


class OllamaProvider(AIProvider):
    """`AIProvider` backed by a local Ollama server."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        min_request_interval: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model or settings.OLLAMA_MODEL
        self._http = RetryingJsonClient(
            base_url=base_url or settings.OLLAMA_BASE_URL,
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
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
            },
        }
        return self._parse(self._http.post_json("/api/chat", payload))

    def _parse(self, document: Any) -> Completion:
        if not isinstance(document, dict):
            raise InvalidAIResponseError("Ollama response was not a JSON object.")

        message = document.get("message")
        if not isinstance(message, dict):
            raise InvalidAIResponseError("Ollama response carried no message object.")

        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise AIResponseBlockedError(
                "Ollama returned no text "
                f"(done_reason={document.get('done_reason') or 'unspecified'})."
            )

        return Completion(
            text=text,
            model=document.get("model") or self._model,
            finish_reason=document.get("done_reason"),
            prompt_tokens=_as_int(document.get("prompt_eval_count")),
            output_tokens=_as_int(document.get("eval_count")),
        )


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None
